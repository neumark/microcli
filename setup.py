#!/usr/bin/env python

from setuptools import setup  # noqa

setup(name="microcli",
      version="0.1",
      description="Extremely-lightweight CLI lib for python",
      long_description=open("README.md").read(),
      author="Peter Neumark",
      author_email="neumark.peter@gmail.com",
      url="https://github.com/neumark/microcli",
      download_url="https://github.com/neumark/microcli",
      install_requires=open('requirements.txt').read().split(),
      py_modules=["microcli"],
      classifiers=[
          "Intended Audience :: Developers",
          "License :: OSI Approved :: Python Software Foundation License",
          "Operating System :: OS Independent",
          "Programming Language :: Python",
          "Topic :: Software Development :: Libraries :: Python Modules",
          "Programming Language :: Python",
          "Programming Language :: Python :: 2",
          "Programming Language :: Python :: 2.6",
          "Programming Language :: Python :: 2.7",
          "Programming Language :: Python :: 3"
          ])
