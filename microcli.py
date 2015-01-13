#!/usr/bin/env python

# To run a single test, run eg:
# python microcli.py MicroCLITestCase.test_varargs

from optparse import (OptionParser, BadOptionError,
                      AmbiguousOptionError, IndentedHelpFormatter)
import inspect
import sys
from functools import wraps
import types
import unittest

COMMAND_ATTR = "_command"
GLOBAL_OPTIONS_STR = "[global options]"
COMMAND_OPTIONS_STR = "[command options]"
ARG_NO_DEFAULT_VALUE = object()


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
                    if not self.allow_interspersed_args:
                        return
                except (BadOptionError, AmbiguousOptionError) as e:
                    # If an argument was not parseable,
                    # pass on the remainig arguments
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

    def __init__(
            self,
            command_definition,
            get_has_global_options=lambda: True,
            initial_indent=0,
            **kwargs):
        CustomHelpFormatter.__init__(self, **kwargs)
        self.current_indent = initial_indent
        self.command_definition = command_definition
        self.get_has_global_options = get_has_global_options

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
        global_options = ""
        if self.get_has_global_options():
            global_options = "[global options] "
        program_and_command = "Usage: %s %s%s" % (
            self.command_definition.opt_parser.get_prog_name(),
            global_options,
            self.command_definition.name)
        vararg_list = ""
        if self.command_definition.varargs is not None:
            vararg_template = " [%(name)s1 %(name)s2 %(name)s3 ... %(name)sN]"
            vararg_list = vararg_template % {
                'name': self.command_definition.varargs}
        options_str = ""
        if len(self.command_definition.opt_parser.option_list) > 0:
            options_str = "%s " % COMMAND_OPTIONS_STR
        return "%(p_and_c)s %(options)s%(args)s%(varargs)s" % {
            'p_and_c': program_and_command,
            'name': self.command_definition.name,
            'args': " ".join(self.command_definition.arg_names),
            'varargs': vararg_list,
            'options': options_str}


class GlobalOptionParser(CustomStderrOptionParser):

    USAGE = "%prog %scommand " +\
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
        self.allow_interspersed_args = False

    def expand_prog_name(self, s):
        global_options = ""
        # > 1 because '-h' is always defined.
        if len(self.option_list) > 1:
            global_options = "%s " % GLOBAL_OPTIONS_STR
        return CustomStderrOptionParser.expand_prog_name(
            self, s) % global_options

    def print_help(self, file=None):
        """ recursively call all command parsers' helps """
        output = file or self.stderr
        CustomStderrOptionParser.print_help(self, output)
        output.write("\nCommands:\n")
        for command_def in self.command_definitions.values():
            command_def.opt_parser.print_help(output)
            output.write("\n")


class CommandOptionParser(CustomStderrOptionParser):

    def __init__(self, command_definition, get_has_global_options, **kwargs):
        formatter = CommandHelpFormatter(
            command_definition,
            get_has_global_options=get_has_global_options,
            initial_indent=4)
        CustomStderrOptionParser.__init__(
            self,
            formatter=formatter,
            **kwargs)
        self.command_definition = command_definition

    def _add_help_option(self):
        """Don't add help option"""
        pass


class CommandDefinition(object):

    def __init__(
            self,
            name,
            opt_parser,
            args_with_defaults,
            fun,
            varargs=None,
            doc=None):
        self.name = name
        self.opt_parser = opt_parser
        self.args_with_defaults = args_with_defaults
        self.arg_names = [a for a, d in args_with_defaults if d == ARG_NO_DEFAULT_VALUE]
        self.fun = fun
        self.varargs = varargs
        self.doc = doc

    def combine_args(self, cli, original_positional_args, kwargs):
        # Converts kwargs to positional args if the function accepts
        # varargs (because python 2 can't call functions with both)
        pos_args = list(original_positional_args)
        combined_arg_list = []
        arg_ix = 0
        for arg_ix in xrange(0, len(self.args_with_defaults)):
            arg_name, default_value = self.args_with_defaults[arg_ix]
            # If the argument has a default value then
            # we should look for it in the kwargs dict
            if default_value != ARG_NO_DEFAULT_VALUE:
                arg_value = kwargs.get(arg_name, default_value)
            else:
                arg_value = pos_args.pop(0)
            combined_arg_list.append(arg_value)
        return combined_arg_list + pos_args

    def verify_function_arity(self, cli, args):
        # receives the list of command line arguments
        # along with the dictionary of kwargs
        # Checks whether the number of arguments is valid
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
            parser_options, positional_args = self.opt_parser.parse_args(args)
            kwargs = parser_options.__dict__
        except UnboundLocalError as e:
            cli.write("Error parsing command arguments")
            return 1  # same as sys.exit(1)
        else:
            self.verify_function_arity(cli, positional_args)
            if self.varargs is None:
                return self.fun(cli, *positional_args, **kwargs)
            return self.fun(cli, *self.combine_args(cli, positional_args, kwargs))

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


def is_string(obj):
    try:
        return isinstance(obj, basestring)
    except NameError:
        return isinstance(obj, str)


def get_undecorated_function(func):
    func_name = func.__name__

    def maybe_wrapped_func(f):
        return hasattr(f, 'cell_contents') and \
            type(f.cell_contents) in [
                types.FunctionType,
                types.MethodType,
                types.UnboundMethodType] and \
            f.cell_contents.__name__ == func_name

    def unpack_func_closure(func):
        while func.func_closure:
            candidates = [f.cell_contents for f in
                          func.func_closure if maybe_wrapped_func(f)]
            if len(candidates) == 0:
                break
            func = candidates[0]
        return func

    def get_wrapped_func(f):
        if hasattr(f, '__wrapped__'):
            # TODO: we may need to keep following this
            # until we no longer have an f.__wrapped__
            return f.__wrapped__
        if hasattr(f, 'func_closure'):
            return unpack_func_closure(f)
        return None

    return get_wrapped_func(func)


class MicroCLI(object):

    def __init__(self, argv=None, stdout=None):
        self.argv = argv if argv is not None else sys.argv
        self.stdout = stdout or sys.stdout
        self.command_definitions = self.get_all_command_definitions()
        self.global_optparser = GlobalOptionParser(
            exit=self.exit,
            command_definitions=self.command_definitions)
        self.default_command = None

    @classmethod
    def exit(cls, exit_code):
        sys.exit(exit_code)

    def write(self, msg, addnewline=True):
        self.stdout.write(str(msg))
        if addnewline:
            self.stdout.write("\n")

    def read_global_options(self):
        global_options, args = self.global_optparser.parse_args(self.argv[1:])
        self.global_options = global_options.__dict__
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
        if is_string(default_value):
            arg_type = "str"
        elif type(default_value) == bool:
            action = bool_actions[default_value]
        elif type(default_value) in [float, int]:
            arg_type = type(default_value).__name__
        add_option_kwargs = {
            'action': action,
            'dest': arg_name,
            'default': default_value}
        if type(default_value) != bool:
            add_option_kwargs['help'] = 'type: %s (default is %s)' % (
                type(default_value).__name__, default_value)
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
        padded_defaults = [ARG_NO_DEFAULT_VALUE] * (len(arg_names) - len(defaults))
        padded_defaults += list(defaults)
        args_with_defaults = list(zip(arg_names, padded_defaults))
        command_definition = CommandDefinition(
            cmd_name,
            None,  # set parser later
            args_with_defaults,
            cmd_fun,
            argspec.varargs,
            self.get_command_description(cmd_fun))
        parser_kwargs = {
            'stderr': self.stdout,
            'exit': self.exit
        }
        if type(cmd_options['parser']) == dict:
            parser_kwargs.update(cmd_options['parser'])
        # The '-h' global option is always there, hence the > 1
        get_has_global_options =\
            lambda: len(self.global_optparser.option_list) > 1
        command_definition.opt_parser = CommandOptionParser(
            command_definition,
            get_has_global_options,
            **parser_kwargs)
        for arg_name, default_value in args_with_defaults:
            if default_value != ARG_NO_DEFAULT_VALUE:
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
        for cmd_name, cmd_data in self.get_commands().items():
            cmd_def = self.get_command_definition(cmd_name, *cmd_data)
            command_definition[cmd_name] = cmd_def
        return command_definition

    @command()
    def help(self):
        """ Print usage """
        self.global_optparser.print_help()
        pass

    @classmethod
    def main(cls, argv=None):
        cli = cls(argv)
        cli.run()

    def run(self):
        self.global_optparser.stderr = self.stdout
        self.arg_list = self.read_global_options()
        self.script_name = self.argv[0]
        command_name = self.default_command
        if self.arg_list:
            command_name = self.arg_list[0]
        if command_name is None:
            self.write(
                "Please specify a command (try " +
                "the 'help' command for usage info)!")
            self.exit(1)
        if command_name in self.command_definitions:
            command_def = self.command_definitions[command_name]
            command_args = self.arg_list[1:]
            result = None
            try:
                result = command_def.run(self, command_args)
            except Exception as e:
                import traceback
                self.write("Error: %s" % str(e))
                self.write("%s" % traceback.format_exc())
                self.exit(1)
            if type(result) == int:
                self.exit(result)
            if result is not None:
                self.write(result)
                self.exit(0)
        else:
            self.write((
                "Unrecognized command '%s' " +
                "(try the 'help' command for usage info)!") % command_name)
            self.exit(1)


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

        @command()
        def f9(self, arg, switch=2, *vararg):
            """a command which accepts args, kwargs and varargs"""
            return "%s,%s,%s" % (len(vararg), switch, arg)

    def __init__(self, *args, **kwargs):
        super(MicroCLITestCase, self).__init__(*args, **kwargs)
        # doing import here so these imports are
        # not dependencies for regular use
        global patch
        global StringIO
        patch = None
        StringIO = None
        try:
            # python 2
            from mock import patch
            from StringIO import StringIO
        except ImportError:
            pass
        try:
            # python 3
            from unittest.mock import patch
            from io import StringIO
        except ImportError:
            pass
        for i in ["patch", "StringIO"]:
            if globals()[i] is None:
                sys.stdout.write("Missing dependency for test: %s\n" % i)
                sys.exit(1)

    def setUp(self):
        super(MicroCLITestCase, self).setUp()

    def test_command_noargs(self):
        """exit value is what the command returns if its an int"""
        with patch("sys.exit") as mock_exit:
            self.T.main(["script_name", "f1"])
            mock_exit.assert_called_with(MicroCLITestCase.RETVAL)

    def test_print_returned_string(self):
        """if the command returns a string it is printed"""
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T("script_name f2 asdf".split())
            cli.stdout = StringIO()
            cli.run()
            self.assertEquals(cli.stdout.getvalue(), "asdf\n")
            # successful execution exits with code 0
            mock_exit.assert_called_with(0)

    def test_kwargs_are_optional(self):
        """kwarg values always have defaults"""
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T("script_name f3".split()).run()
            # kwargs are optional
            mock_exit.assert_called_with(4)

    def test_kwargs_are_passed(self):
        """kwarg values are passed as expected"""
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T(
                "script_name f3 --awesome-option 1".split()).run()
            mock_exit.assert_called_with(1)
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T(
                "script_name f3 --awesome-option 1234567".split()).run()
            mock_exit.assert_called_with(7)

    def test_mixing_args_and_kwargs(self):
        """kwarg values can be mixed with arg values"""
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T("script_name f4 --kwopt c a b".split())
            cli.stdout = StringIO()
            cli.run()
            self.assertEquals(cli.stdout.getvalue(), "a,b,c\n")
            # successful execution exits with code 0
            mock_exit.assert_called_with(0)

    def test_global_options(self):
        """test the global option parser"""
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T("script_name --some-option 67 f5".split())
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
                "script_name --some-option 67 f5 --cmd-specific-arg 13".split())
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
                "script_name --some-option 67 f5 --cmd-specific-arg".split())
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
            cli = MicroCLITestCase.T(["script_name", "f4"])
            cli.command_definitions["f4"].verify_function_arity(cli, [])
            mock_exit.assert_called_with(1)

    def test_varargs(self):
        """varargs are properly passed into the function"""
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T("script_name f6 a b c d e f g h i".split())
            cli.stdout = StringIO()
            cli.run()
            self.assertEquals(cli.stdout.getvalue(), "a,b,7\n")
            # successful execution exits with code 0
            mock_exit.assert_called_with(0)

    def test_varargs_with_kwargs(self):
        """varargs and kwargs can be used together"""
        with patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T("script_name f9 --switch 3 arg b c d e f g h i".split())
            cli.stdout = StringIO()
            cli.run()
            self.assertEquals(cli.stdout.getvalue(), "8,3,arg\n")
            # successful execution exits with code 0
            mock_exit.assert_called_with(0)

    def test_kwarg_type(self):
        """kwarg values have the type of their default arguments"""
        with patch.object(MicroCLI, "exit") as mock_exit:
            cli = MicroCLITestCase.T([
                "script_name",
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
            cli = MicroCLITestCase.T(["script_name", "help"], StringIO())
            cli.run()
            output = cli.stdout.getvalue()
            print output
            self.assertTrue(output.startswith("Usage: "))
            # successful execution exits with code 0
            mock_exit.assert_called_with(0)

    def test_parser_options(self):
        """parser options can be passed as an argument to @command()"""
        with patch("sys.exit") as mock_exit:
            argv = "script_name f8 -a b --c d e f g h i".split()
            cli = MicroCLITestCase.T(argv, StringIO())
            cli.run()
            self.assertEquals(
                cli.stdout.getvalue(),
                "%s\n" % " ".join(argv[2:]))
            # successful execution exits with code 0
            mock_exit.assert_called_with(0)

    def test_command_vs_global_options(self):
        """Options following the command name are command options"""
        with patch.object(MicroCLI, "exit") as mock_exit:
            # --cmd-specific-arg is both a global and a command option.
            cli = MicroCLITestCase.T(
                "script_name --cmd-specific-arg 51 f5 --cmd-specific-arg 53".split())
            cli.global_optparser.add_option(
                '--cmd-specific-arg',
                action='store',
                dest="some_option")
            cli.run()
            mock_exit.assert_called_with(104)

    def test_options_in_usage(self):
        """Global or command options should only appear
           in the usage message if they apply."""

        class NoGlobal(MicroCLI):

            @command()
            def no_kwargs(self):
                return MicroCLITestCase.RETVAL

            @command()
            def has_kwargs(self, some_option=2):
                return MicroCLITestCase.RETVAL

        class HasGlobal(MicroCLI):

            def __init__(self, *args, **kwargs):
                super(HasGlobal, self).__init__(*args, **kwargs)
                self.global_optparser.add_option(
                    '--some-option',
                    action='store',
                    dest="some_option")

            @command()
            def f1(self):
                return MicroCLITestCase.RETVAL

        with patch("sys.exit") as mock_exit:
            no_global = NoGlobal(['script_name', '-h'])
            has_global = HasGlobal(['script_name', '-h'])
            # Test if [global options] is part of the usage string
            buf = StringIO()
            no_global.global_optparser.print_usage(buf)
            self.assertFalse(GLOBAL_OPTIONS_STR in buf.getvalue())
            buf = StringIO()
            has_global.global_optparser.print_usage(buf)
            self.assertTrue(GLOBAL_OPTIONS_STR in buf.getvalue())
            self.assertTrue(
                COMMAND_OPTIONS_STR in
                no_global.command_definitions['has_kwargs'].
                opt_parser.formatter.get_command_usage())
            self.assertFalse(
                COMMAND_OPTIONS_STR in
                no_global.command_definitions['no_kwargs'].
                opt_parser.formatter.get_command_usage())

    # TODO: test unrecognized command
    # TODO: test default command
    # TODO: test kwarg types reflected in help
    # TODO: test error thrown if kwarg command option value has incorrect type


def suite():
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTest(loader.loadTestsFromTestCase(MicroCLITestCase))
    return suite

if __name__ == "__main__":
    unittest.main(
        defaultTest="suite",
        testRunner=unittest.TextTestRunner(verbosity=2))
