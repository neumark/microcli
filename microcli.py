#!/usr/bin/env python
from argparse import ArgumentParser
import inspect
import sys
import os
from functools import wraps
import types
# needed for tests
import unittest
from mock import patch

USAGE = "Usage: fibi [options] command [command args]"
EXAMPLES = """Examples:
    TODO
"""
COMMAND_ATTR = "_command"

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

class MicroCLI(object):

    def __init__(self):
        self.parser = ArgumentParser()
        self.stdout = sys.stdout

    def write(self, msg, addnewline=True):
        self.stdout.write(msg)
        if addnewline:
            self.stdout.write("\n")

    def read_options(self, arguments=None):
        (options, args) = self.parser.parse_args(arguments or sys.argv[1:])
        self.options = options
        if len(args) < 1:
            return ["help"]
        return args

    @command
    def help(self, *args, **kwargs):
        """ Print usage """
        self.parser.print_help()
        self.write("Commands:")
        for i in dir(self.__class__):
            cmd = getattr(self, i)
            if i[0] != "_" and getattr(cmd, COMMAND_ATTR, None) is not None:
                arg_names = ", ".join(self.get_arg_names(cmd))
                if arg_names:
                    arg_names = "(%s)" % arg_names
                self.write("* %s%s\n    %s" % (i, arg_names, getattr(cmd, '__doc__', '(no docstring for function)')))
        self.write("\n" + EXAMPLES)

    @classmethod
    def get_arg_names(cls, fun):
        # note: the first argument for a command function is self.
        return inspect.getargspec(get_undecorated_function(fun)).args[1:]

    def main(self):
        arguments = self.read_options()
        command_name = arguments[0]
        command_fun = getattr(self, command_name, self.help)
        named_args = self.get_arg_names(command_fun)
        command_args = arguments[1:]
        if len(command_args) != len(named_args):
            self.write("Expected %s arguments, got %s")
            self.write("Expected arguments: %s" % ", ".join(named_args))
        try:
            result = command_fun(*command_args)
        except Exception, e:
            self.write(str(e))
            sys.exit(1)
        if result is not None:
            self.write(result)
        sys.exit(result if type(result) == int else 0)

class MicroCLITestCase(unittest.TestCase):

    def test_command(self):
        RETVAL = 15
        class T(MicroCLI):
            @command
            def f(self):
                return RETVAL
        with patch("sys.exit") as mock_exit:
            mock_exit.assert_called_with(RETVAL)


def suite():
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTest(loader.loadTestsFromTestCase(MicroCLITestCase))
    return suite

if __name__ == "__main__":
    unittest.main(defaultTest="suite", testRunner=unittest.TextTestRunner(verbosity=2))
