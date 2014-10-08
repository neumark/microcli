MicroCLI
==========
![Travis CI status](https://travis-ci.org/neumark/microcli.svg)

*A minimal CLI framework for python*
MicroCLI provide an easy way to create command line utilities
which can perform several related actions. [One example](https://github.com/neumark/microcli/blob/master/example.py) is a calculator which can add, subtract and 
compute logarithms. This is implemented in ```example.py```

Installation
---

```
pip install microcli
```

or -if you want the bleeding edge-

```
pip install -e git+git@github.com:neumark/microcli.git@master#egg=microcli

```

Example Usage
---
To demonstrate the API on a very simple example, consider
the following code in a file named foobar.py:

```python
#!/usr/bin/env python
from microcli import MicroCLI, command

class FooBarCommand(MicroCLI):

    @command()
    def foo(self):
        return "foo"

    @command()
    def bar(self, arg1, arg2="four"):
        return "%s = %s" % (arg1, arg2)

if __name__ == "__main__":
    FooBarCommand.main()
```

This could be used on the command line like this:

```
$ foobar.py foo     # prints "foo"
$ foobar.py bar 4   # prints "4 = four"
$ foobar.py bar --arg2 good microcli  # prints "microcli = good"
$ foobar.py -h      # print usage info
```

Dependencies
---
None. At least none to run MicroCLI. For tests under python2, the contents of requirements-test.txt must be installed in the current virtualenv or globally.
