#!/usr/bin/env python
from microcli import MicroCLI, command
from math import log

class Calculator(MicroCLI):

    def __init__(self, *args, **kwargs):
        super(Calculator, self).__init__(*args, **kwargs)
        # register global option
        self.global_optparser.add_option(
            '--output-hex',
            action='store_true',
            default=False,
            dest='output_hex',
            help='Print result in hexadecimal')

    # not all functions are commands, only those
    # decorated with @command()
    def _format_result(self, result):
        if self.global_options['output_hex']:
            template = "%x"
        else:
            template = "%s"
        return template % result

    @command()
    def add(self, *number):
        """Adds all parameters interpreted as integers"""
        return self._format_result(sum(
            # positional arguments are always strings
            [int(n) for n in number]))

    @command()
    def subtract(self, number1, number2):
        """Subtracts number2 from number1"""
        return self._format_result(int(number1) - int(number2))

    @command()
    def log(self, x, base=2):
        """Computes the logarithm of x with the given base
         (the default base is 2)."""
        return self._format_result(log(float(x), base))

if __name__ == "__main__":
    Calculator.main()

