#!/usr/bin/env python
from optparse import (OptionParser,BadOptionError,AmbiguousOptionError)
import inspect
import sys
import os
from functools import wraps
import types
import unittest

USAGE = "Usage: fibi [options] command [command args]"
EXAMPLES = """Examples:
    TODO
"""
COMMAND_ATTR = "_command"

# from http://stackoverflow.com/questions/1885161/how-can-i-get-optparses-optionparser-to-ignore-invalid-options
class PassThroughOptionParser(OptionParser):
    """
    An unknown option pass-through implementation of OptionParser.

    When unknown arguments are encountered, bundle with largs and try again,
    until rargs is depleted.  

    sys.exit(status) will still be called if a known argument is passed
    incorrectly (e.g. missing arguments or bad argument types, etc.)        
    """
    def _process_args(self, largs, rargs, values):
        while rargs:
            try:
                OptionParser._process_args(self,largs,rargs,values)
            except (BadOptionError,AmbiguousOptionError), e:
                largs.append(e.opt_str)

class CommandDefinition(object):

    def __init__(self,
            name,
            opt_parser,
            arg_names,
            fun,
            doc=None):
        self.name = name
        self.opt_parser = opt_parser
        self.arg_names = arg_names
        self.fun = fun
        self.doc = doc

    def arg_check(self, cli, args):
        if len(args) != len(self.arg_names):
            cli.write("Expected %s arguments, got %s" % (len(self.arg_names), len(args)))
            cli.write("Expected arguments: %s" % ", ".join(self.arg_names))
            sys.exit(1)

    def run(self, cli, args):
        try:
            kwargs, parsed_args = self.opt_parser.parse_args(args)
        except UnboundLocalError, e:
            cli.write("Error parsing command arguments")
            return 1 #  same as sys.exit(1)
        else:
            self.arg_check(cli, parsed_args)
            return self.fun(cli, *parsed_args, **values_to_dict(kwargs))


def command(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        return func(self, *args, **kwargs)
    setattr(wrapper, COMMAND_ATTR, True)
    return wrapper

def get_undecorated_function(func):
    func_name = func.__name__
    def maybe_wrapped_func(f):
        return hasattr(f, 'cell_contents') and \
            type(f.cell_contents) in [types.FunctionType, types.MethodType, types.UnboundMethodType] and \
            f.cell_contents.__name__ == func_name
    while func.func_closure:
        candidates = [f.cell_contents for f in func.func_closure if maybe_wrapped_func(f)]
        if len(candidates) == 0:
            break
        func = candidates[0]
    return func

def values_to_dict(values):
    return values.__dict__


class MicroCLI(object):

    def __init__(self, argv=None):
        self.argv = argv if argv is not None else sys.argv[1:]
        self.global_optparser = PassThroughOptionParser()
        self.stdout = sys.stdout
        self.default_command = "help"
        self.command_definitions = self.get_all_command_definitions()

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
            arg_type="str"
        elif type(default_value) == bool:
            action = bool_actions[default_value]
        elif type(default_value) in [float, int]:
            arg_type=type(default_value).__name__
        add_option_kwargs = {
            'action': action,
            'dest': arg_name,
            'default': default_value}
        if arg_type is not None:
            add_option_kwargs['type'] = arg_type
        parser.add_option('--%s' % cls.kwarg_name_to_option_name(arg_name), **add_option_kwargs)

    @classmethod
    def get_command_definition(cls, cmd_name, cmd_fun):
        #def f1(a0, a1, kw0="a", *args, **kwargs):
        #ArgSpec(args=['a0', 'a1', 'kw0'], varargs='args', keywords='kwargs', defaults=('a',))
        # get positional arguments
        argspec = inspect.getargspec(get_undecorated_function(cmd_fun))
        # note: the first argument for a command method is self.
        arg_names = argspec.args[1:]
        defaults = argspec.defaults or []
        padded_defaults = [None] * (len(arg_names) - len(defaults)) + list(defaults)
        args_with_defaults = zip(arg_names, padded_defaults)
        parser = OptionParser()
        for arg_name, default_value in args_with_defaults:
            if default_value is not None:
                cls.add_parser_option(parser, arg_name, default_value)
        return CommandDefinition(
                cmd_name,
                parser,
                [a for a,d in args_with_defaults if d is None],
                cmd_fun,
                cls.get_command_description(cmd_fun))


    @classmethod
    def get_commands(cls):
        command_dict = {}
        for i in dir(cls):
            cmd = getattr(cls, i)
            if getattr(cmd, COMMAND_ATTR, None) is not None:
                command_dict[i] = cmd
        return command_dict

    @classmethod
    def get_command_description(cls, cmd_fun):
        return getattr(cmd_fun, '__doc__', None)

    @classmethod
    def get_all_command_definitions(cls):
        command_definition = {}
        for cmd_name, cmd_fun in cls.get_commands().iteritems():
            cmd_def = cls.get_command_definition(cmd_name, cmd_fun)
            command_definition[cmd_name] = cmd_def
        return command_definition

    @command
    def help(self, *args, **kwargs):
        """ Print usage """
        pass

    @classmethod
    def main(cls, argv=None):
        cli = cls(argv)
        cli.run()

    def run(self):
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
        except Exception, e:
            import traceback
            self.write("Error: %s" % str(e))
            self.write("%s" % traceback.format_exc())
            sys.exit(1)
        if type(result) in [str, unicode]:
            self.write(result)
        sys.exit(result if type(result) == int else 0)

class MicroCLITestCase(unittest.TestCase):

    RETVAL = 15

    class T(MicroCLI):
        @command  # simple command: no parameters
        def f1(self):
            return MicroCLITestCase.RETVAL
        @command  # a command with only positional arguments
        def f2(self, a):
            return a
        @command  # a command with only keyword arguments
        def f3(self, awesome_option="asdf"):
            return len(awesome_option)
        @command  # a command with both positional and keyword arguments
        def f4(self, arg1, arg2, kwopt="asdf"):
            return "%s,%s,%s" % (arg1, arg2, kwopt)
        @command  # a command the uses global options
        def f5(self, cmd_specific_arg=2):
            return int(self.global_options['some_option'])+int(cmd_specific_arg)


    def __init__(self, *args, **kwargs):
        super(MicroCLITestCase, self).__init__(*args, **kwargs)
        # doing import here so mock is not a dependency for regular use
        try:
            from mock import patch
            self.patch = patch
        except ImportError:
            print "Missing dependency for test: mock"
            sys.exit(1)

    def setUp(self):
        super(MicroCLITestCase, self).setUp()

    def test_command_noargs(self):
        """exit value is what the command returns if its an int"""
        with self.patch("sys.exit") as mock_exit:
            self.T.main(["f1"])
            mock_exit.assert_called_with(MicroCLITestCase.RETVAL)

    def test_print_returned_string(self):
        """if the command returns a string it is printed"""
        from StringIO import StringIO
        with self.patch("sys.exit") as mock_exit:
            stdout = StringIO()
            cli = MicroCLITestCase.T("f2 asdf".split())
            cli.stdout = stdout
            cli.run()
            self.assertEquals(stdout.getvalue(), "asdf\n")
            # successful execution exits with code 0
            mock_exit.assert_called_with(0)

    def test_kwargs_are_optional(self):
        """kwarg values always have defaults"""
        with self.patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T("f3".split()).run()
            # kwargs are optional
            mock_exit.assert_called_with(4)

    def test_kwargs_are_passed(self):
        """kwarg values are passed as expected"""
        with self.patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T("f3 --awesome-option 1".split()).run()
            mock_exit.assert_called_with(1)
        with self.patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T("f3 --awesome-option 1234567".split()).run()
            mock_exit.assert_called_with(7)

    def test_mixing_args_and_kwargs(self):
        """kwarg values can be mixed with arg values"""
        from StringIO import StringIO
        with self.patch("sys.exit") as mock_exit:
            stdout = StringIO()
            cli = MicroCLITestCase.T("f4 --kwopt c a b".split())
            cli.stdout = stdout
            cli.run()
            self.assertEquals(stdout.getvalue(), "a,b,c\n")
            # successful execution exits with code 0
            mock_exit.assert_called_with(0)

    def test_global_options(self):
        """test the global option parser"""
        with self.patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T("--some-option 67 f5".split())
            cli.global_optparser.add_option(
                    '--some-option',
                    action='store',
                    dest="some_option")
            cli.run()
            mock_exit.assert_called_with(67+2)

    def test_mixing_global_and_cmd_options(self):
        """test the global option parser"""
        with self.patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T("--some-option 67 f5 --cmd-specific-arg 13".split())
            cli.global_optparser.add_option(
                    '--some-option',
                    action='store',
                    dest="some_option")
            cli.run()
            mock_exit.assert_called_with(67+13)

    def test_missing_arg_value(self):
        """test what happends when the value of a kwarg is missing"""
        with self.patch("sys.exit") as mock_exit:
            cli = MicroCLITestCase.T("--some-option 67 f5 --cmd-specific-arg".split())
            cli.global_optparser.add_option(
                    '--some-option',
                    action='store',
                    dest="some_option")
            cli.run()
            mock_exit.assert_called_with(1)


def suite():
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTest(loader.loadTestsFromTestCase(MicroCLITestCase))
    return suite

if __name__ == "__main__":
    unittest.main(defaultTest="suite", testRunner=unittest.TextTestRunner(verbosity=2))
