#!/usr/bin/env python
from optparse import (OptionParser, BadOptionError,
                      AmbiguousOptionError, IndentedHelpFormatter)
import inspect
import sys
from functools import wraps
import types
import unittest

COMMAND_ATTR = "_command"


class CustomStderrOptionParser(OptionParser):

    def __init__(
            self,
            stderr=sys.stderr,
            exit=sys.exit,
            ignore_unknown=False,
            **kwargs):
        OptionParser.__init__(self, **kwargs)
        self.exit_impl = exit
        self.stderr = stderr
        self.ignore_unknown = ignore_unknown

    def _process_args(self, largs, rargs, values):
        if not self.ignore_unknown:
            OptionParser._process_args(self, largs, rargs, values)
        else:
            # from http://stackoverflow.com/questions/1885161/
            #    how-can-i-get-optparses-optionparser-to-ignore-invalid-options
            while rargs:
                try:
                    OptionParser._process_args(self, largs, rargs, values)
                except (BadOptionError, AmbiguousOptionError) as e:
                    largs.append(e.opt_str)

    def print_usage(self, file=None):
        return OptionParser.print_usage(self, file or self.stderr)

    def print_help(self, file=None):
        return OptionParser.print_help(self, file or self.stderr)

    def exit(self, status=0, msg=None):
        if msg:
            self.stderr.write(msg)
        self.exit_impl(status)

    def error(self, msg):
        self.print_usage(self.stderr)
        self.exit(2, "%s: error: %s\n" % (self.get_prog_name(), msg))


class CustomHelpFormatter(IndentedHelpFormatter):

    options_heading = "Global options"

    def _indent(self, msg):
        return "%*s%s" % (self.current_indent, "", msg)

    def format_heading(self, _heading):
        # _heading is always "Options:"
        return self._indent("%s:\n" % self.options_heading)


class CommandHelpFormatter(CustomHelpFormatter):

    options_heading = "Command options"

    def __init__(self, command_definition, initial_indent=0, **kwargs):
        CustomHelpFormatter.__init__(self, **kwargs)
        self.current_indent = initial_indent
        self.command_definition = command_definition

    def format_usage(self, usage):
        command_help = self.command_definition.doc
        if command_help is not None:
            template = "%s: %s\n"
            values = (self.command_definition.name, command_help)
        else:
            template = "%s\n"
            values = (self.command_definition.name)
        return self._indent(template % values) +\
            self._indent(self.get_command_usage())

    def get_command_usage(self):
        if self.command_definition.varargs is None and\
                len(self.command_definition.arg_names) == 0:
            return "Usage: %s [options]" % self.command_definition.name
        vararg_list = ""
        if self.command_definition.varargs is not None:
            vararg_template = " [%(name)s1 %(name)s2 %(name)s3 ... %(name)sN]"
            vararg_list = vararg_template % {
                'name': self.command_definition.varargs}
        return "Usage: %(name)s %(args)s%(varargs)s" % {
            'name': self.command_definition.name,
            'args': " ".join(self.command_definition.arg_names),
            'varargs': vararg_list}


class GlobalOptionParser(CustomStderrOptionParser):

    USAGE = "%prog [global options] command " +\
            "[command options] command arguments"

    def __init__(self, command_definitions=None, **kwargs):
        formatter = CustomHelpFormatter()
        CustomStderrOptionParser.__init__(
            self,
            formatter=formatter,
            ignore_unknown=True,
            usage=GlobalOptionParser.USAGE,
            **kwargs)
        self.command_definitions = command_definitions

    def print_help(self, file=None):
        """ recursively call all command parsers' helps """
        output = file or self.stderr
        CustomStderrOptionParser.print_help(self, output)
        output.write("\nCommands:\n")
        for command_def in self.command_definitions.values():
            command_def.opt_parser.print_help(output)
            output.write("\n")


class CommandOptionParser(CustomStderrOptionParser):

    def __init__(self, command_definition, **kwargs):
        formatter = CommandHelpFormatter(
            command_definition,
            initial_indent=4)
        CustomStderrOptionParser.__init__(
            self,
            formatter=formatter,
            **kwargs)
        self.command_definition = command_definition


class CommandDefinition(object):

    def __init__(
            self,
            name,
            opt_parser,
            arg_names,
            fun,
            varargs=None,
            doc=None):
        self.name = name
        self.opt_parser = opt_parser
        self.arg_names = arg_names
        self.fun = fun
        self.varargs = varargs
        self.doc = doc

    def arg_check(self, cli, args):
        if self.varargs is not None and (len(args) >= len(self.arg_names)):
            return  # if the function accepts varargs, we're good.
        if len(args) != len(self.arg_names):
            error_template = "Expected %s arguments, got %s"
            if self.varargs is not None:
                error_template = "Expected at least %s arguments, got %s"
            cli.write(error_template % (
                len(self.arg_names),
                len(args)))
            cli.write("Expected arguments: %s" % ", ".join(self.arg_names))
            cli.exit(1)

    def run(self, cli, args):
        try:
            kwargs, parsed_args = self.opt_parser.parse_args(args)
        except UnboundLocalError as e:
            cli.write("Error parsing command arguments")
            return 1  # same as sys.exit(1)
        else:
            self.arg_check(cli, parsed_args)
            return self.fun(cli, *parsed_args, **values_to_dict(kwargs))


def command(parser_options=None):
    options = {
        'parser': parser_options
    }

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            return func(self, *args, **kwargs)
        setattr(wrapper, COMMAND_ATTR, options)
        return wrapper
    return decorator


def get_undecorated_function(func):
    func_name = func.__name__

    def maybe_wrapped_func(f):
        return hasattr(f, 'cell_contents') and \
            type(f.cell_contents) in [
                types.FunctionType,
                types.MethodType,
                types.UnboundMethodType] and \
            f.cell_contents.__name__ == func_name
    while func.func_closure:
        candidates = [f.cell_contents for f in
                      func.func_closure if maybe_wrapped_func(f)]
        if len(candidates) == 0:
            break
        func = candidates[0]
    return func


def values_to_dict(values):
    return values.__dict__


class MicroCLI(object):

    def __init__(self, argv=None, stdout=None):
        self.argv = argv if argv is not None else sys.argv[1:]
        self.stdout = stdout or sys.stdout
        self.command_definitions = self.get_all_command_definitions()
        self.global_optparser = GlobalOptionParser(
            exit=self.exit,
            command_definitions=self.command_definitions)
        self.default_command = "help"

    @classmethod
    def exit(cls, exit_code):
        sys.exit(exit_code)

    def write(self, msg, addnewline=True):
        self.stdout.write(str(msg))
        if addnewline:
            self.stdout.write("\n")

    def read_global_options(self):
        global_options, args = self.global_optparser.parse_args(self.argv)
        self.global_options = global_options.__dict__
        if len(args) < 1:
            return [self.default_command]
        return args

    @classmethod
    def kwarg_name_to_option_name(cls, kwarg_name):
        return kwarg_name.replace("_", "-")

    @classmethod
    def add_parser_option(cls, parser, arg_name, default_value):
        action = "store"
        arg_type = None
        bool_actions = {
            True: 'store_false',
            False: 'store_true'}
        if type(default_value) in [str, unicode]:
            arg_type = "str"
        elif type(default_value) == bool:
            action = bool_actions[default_value]
        elif type(default_value) in [float, int]:
            arg_type = type(default_value).__name__
        add_option_kwargs = {
            'action': action,
            'dest': arg_name,
            'default': default_value}
        if arg_type is not None:
            add_option_kwargs['type'] = arg_type
        parser.add_option(
            '--%s' % cls.kwarg_name_to_option_name(arg_name),
            **add_option_kwargs)

    def get_command_definition(self, cmd_name, cmd_fun, cmd_options):
        # get positional arguments
        argspec = inspect.getargspec(get_undecorated_function(cmd_fun))
        # note: the first argument for a command method is self.
        arg_names = argspec.args[1:]
        defaults = argspec.defaults or []
        padded_defaults = [None] * (len(arg_names) - len(defaults))
        padded_defaults += list(defaults)
        args_with_defaults = zip(arg_names, padded_defaults)
        command_definition = CommandDefinition(
            cmd_name,
            None,  # set parser later
            [a for a, d in args_with_defaults if d is None],
            cmd_fun,
            argspec.varargs,
            self.get_command_description(cmd_fun))
        parser_kwargs = {
            'stderr': self.stdout,
            'exit': self.exit
        }
        if type(cmd_options['parser']) == dict:
            parser_kwargs.update(cmd_options['parser'])
        command_definition.opt_parser = CommandOptionParser(
            command_definition, **parser_kwargs)
        for arg_name, default_value in args_with_defaults:
            if default_value is not None:
                self.add_parser_option(
                    command_definition.opt_parser,
                    arg_name,
                    default_value)
        return command_definition

    @classmethod
    def get_commands(cls):
        command_dict = {}
        for i in dir(cls):
            cmd = getattr(cls, i)
            if type(getattr(cmd, COMMAND_ATTR, False)) == dict:
                command_dict[i] = (cmd, getattr(cmd, COMMAND_ATTR))
        return command_dict

    @classmethod
    def get_command_description(cls, cmd_fun):
        return getattr(cmd_fun, '__doc__', None)

    def get_all_command_definitions(self):
        command_definition = {}
        for cmd_name, cmd_data in self.get_commands().iteritems():
            cmd_def = self.get_command_definition(cmd_name, *cmd_data)
            command_definition[cmd_name] = cmd_def
        return command_definition

    @command()
    def help(self, *args, **kwargs):
        """ Print usage """
        pass

    @classmethod
    def main(cls, argv=None):
        cli = cls(argv)
        cli.run()

    def run(self):
        self.global_optparser.stderr = self.stdout
        self.arg_list = self.read_global_options()
        command_name = self.arg_list[0] if self.arg_list else None
        if command_name in self.command_definitions:
            command_def = self.command_definitions[command_name]
        else:
            command_def = self.command_definitions[self.default_command]
        command_args = self.arg_list[1:]
        result = None
        try:
            result = command_def.run(self, command_args)
        except Exception as e:
            import traceback
            self.write("Error: %s" % str(e))
            self.write("%s" % traceback.format_exc())
            self.exit(1)
        if type(result) in [str, unicode]:
            self.write(result)
        self.exit(result if type(result) == int else 0)


class MicroCLITestCase(unittest.TestCase):

    RETVAL = 15

    class T(MicroCLI):
        @command()
        def f1(self):
            """simple command: no parameters"""
            return MicroCLITestCase.RETVAL

        @command()
        def f2(self, a):
            """a command with only positional arguments"""
            return a

        @command()
        def f3(self, awesome_option="asdf"):
            """a command with only keyword arguments"""
            return len(awesome_option)

        @command()
        def f4(self, arg1, arg2, kwopt="asdf"):
            """a command with both positional and keyword arguments"""
            return "%s,%s,%s" % (arg1, arg2, kwopt)

        @command()
        def f5(self, cmd_specific_arg=2):
            """a command that uses global options"""
            return (int(self.global_options['some_option']) +
                    int(cmd_specific_arg))

        @command()
        def f6(self, arg1, arg2, *vararg):
            """a command which accepts varargs"""
            return "%s,%s,%s" % (arg1, arg2, len(vararg))

        @command()
        def f7(self, int_option=0, float_option=0.1, bool_option1=True,
               bool_option2=False, string_option="asdf"):
            """a command to test the types of kwargs"""
            return "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s" % (
                type(int_option).__name__,
                str(int_option),
                type(float_option).__name__,
                str(float_option),
                type(bool_option1).__name__,
                str(bool_option1),
                type(bool_option2).__name__,
                str(bool_option2),
                type(string_option).__name__,
                str(string_option))

        @command(parser_options={'ignore_unknown': True})
        def f8(self, *option):
            """command parsers can treat unknown options as varargs"""
            return " ".join(option)

    def __init__(self, *args, **kwargs):
        super(MicroCLITestCase, self).__init__(*args, **kwargs)
        # doing import here so these imports are
        # not dependencies for regular use
        try:
            global patch
            global StringIO
            from mock import patch
            from StringIO import StringIO
        except ImportError:
            sys.stdout.write("Missing dependency for test: mock\n")
            sys.exit(1)

    def setUp(self):
        super(MicroCLITestCase, self).setUp()

    def test_command_noargs(self):
        """exit value is what the command returns if its an int"""
        with patch("sys.exit") as mock_exit:
            self.T.main(["f1"])
            mock_exit.assert_called_with(MicroCLITestCase.RETVAL)

    def test_print_returned_string(self):
        """if the command returns a string it is printed"""
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T("f2 asdf".split())
            cli.stdout = StringIO()
            cli.run()
            self.assertEquals(cli.stdout.getvalue(), "asdf\n")
            # successful execution exits with code 0
            mock_exit.assert_called_with(0)

    def test_kwargs_are_optional(self):
        """kwarg values always have defaults"""
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T("f3".split()).run()
            # kwargs are optional
            mock_exit.assert_called_with(4)

    def test_kwargs_are_passed(self):
        """kwarg values are passed as expected"""
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T(
                "f3 --awesome-option 1".split()).run()
            mock_exit.assert_called_with(1)
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T(
                "f3 --awesome-option 1234567".split()).run()
            mock_exit.assert_called_with(7)

    def test_mixing_args_and_kwargs(self):
        """kwarg values can be mixed with arg values"""
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T("f4 --kwopt c a b".split())
            cli.stdout = StringIO()
            cli.run()
            self.assertEquals(cli.stdout.getvalue(), "a,b,c\n")
            # successful execution exits with code 0
            mock_exit.assert_called_with(0)

    def test_global_options(self):
        """test the global option parser"""
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T("--some-option 67 f5".split())
            cli.global_optparser.add_option(
                '--some-option',
                action='store',
                dest="some_option")
            cli.run()
            mock_exit.assert_called_with(67+2)

    def test_mixing_global_and_cmd_options(self):
        """test the global option parser"""
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T(
                "--some-option 67 f5 --cmd-specific-arg 13".split())
            cli.global_optparser.add_option(
                '--some-option',
                action='store',
                dest="some_option")
            cli.run()
            mock_exit.assert_called_with(67+13)

    def test_missing_kwarg_value(self):
        """test what happends when the value of a kwarg is missing"""
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T(
                "--some-option 67 f5 --cmd-specific-arg".split())
            cli.global_optparser.add_option(
                '--some-option',
                action='store',
                dest="some_option")
            cli.run()
            mock_exit.assert_called_with(1)

    def test_missing_arg(self):
        """test what happends when not enough
           arguments are passed to a function"""
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T(["f4"])
            cli.command_definitions["f4"].arg_check(cli, [])
            mock_exit.assert_called_with(1)

    def test_varargs(self):
        """varargs are properly passed into the function"""
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T("f6 a b c d e f g h i".split())
            cli.stdout = StringIO()
            cli.run()
            self.assertEquals(cli.stdout.getvalue(), "a,b,7\n")
            # successful execution exits with code 0
            mock_exit.assert_called_with(0)

    def test_kwarg_type(self):
        """kwarg values have the type of their default arguments"""
        with patch.object(MicroCLI, "exit") as mock_exit:
            cli = MicroCLITestCase.T([
                "f7",
                "--int-option", "1",
                "--float-option", "2.5",
                "--bool-option1",
                "--bool-option2",
                "--string-option", "alma"])
            cli.stdout = StringIO()
            cli.run()
            self.assertEquals(
                cli.stdout.getvalue(),
                "int,1,float,2.5,bool,False,bool,True,str,alma\n")
            # successful execution exits with code 0
            mock_exit.assert_called_with(0)

    def test_help(self):
        """defined commands appear in the help message"""
        with patch.object(MicroCLI, "exit") as mock_exit:
            cli = MicroCLITestCase.T(["-h"], StringIO())
            cli.run()
            output = cli.stdout.getvalue()
            self.assertTrue(output.startswith("Usage: "))
            print output
            # successful execution exits with code 0
            mock_exit.assert_called_with(0)

    def test_parser_options(self):
        """parser options can be passed as an argument to @command()"""
        with patch("sys.exit") as mock_exit:
            argv = "f8 -a b --c d e f g h i".split()
            cli = MicroCLITestCase.T(argv, StringIO())
            cli.run()
            self.assertEquals(
                cli.stdout.getvalue(),
                "%s\n" % " ".join(argv[1:]))
            # successful execution exits with code 0
            mock_exit.assert_called_with(0)


def suite():
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTest(loader.loadTestsFromTestCase(MicroCLITestCase))
    return suite

if __name__ == "__main__":
    unittest.main(
        defaultTest="suite",
        testRunner=unittest.TextTestRunner(verbosity=2))
