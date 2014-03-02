import os
import sys
from collections import OrderedDict

from invoke import task

from .utils import load_module, split_args


@task(help={
    'state':'Two-letter state-abbreviation, e.g. NY',
})
def list(state):
    """
    Show available validations for state.

    """
    state_mod = load_module(state, ['validate'])
    print "\nAvailable validators:\n"
    for name in dir(state_mod.validate):
        if name.startswith('validate_'):
            func = getattr(state_mod.validate, name)
            out = "\t%s" % name
            if func.func_doc:
                out += "\n\t\t %s" % func.func_doc
            print out + "\n"

@task(help={
    'state':'Two-letter state-abbreviation, e.g. NY',
    'include': 'Validations to run (comma-separated list)',
    'exclude': 'Validations to skip (comma-separated list)',
})
def run(state, include=None, exclude=None):
    """
    Run data validations for state.

    State is required. Optionally filter validations using include/exclude flags.
    """
    if include and exclude:
        sys.exit("ERROR: You can not use both include and exclude flags!")

    state_mod = load_module(state, ['validate'])
    # Load all validations in order found
    validations = OrderedDict()
    for name in dir(state_mod.validate):
        if name.startswith('validate_'):
            func = getattr(state_mod.validate, name)
            validations[name] = func

    # Filter validations based in include/exclude flags
    if include:
        to_run = split_args(include)
        for val in validations:
            if val not in to_run:
                validations.pop(val)
    if exclude:
        to_skip = split_args(exclude)
        for val in validations:
            if val in to_skip:
                validations.pop(val)

    # Run remaining validations
    run_validation(state, validations.values()) 


def run_validation(state, validators):
    passed = []
    failed = []
    print
    for validator in validators:
        try:
            validator()
            passed.append(validator.__name__)
        except Exception as e:
            failed.append("Error: %s - %s - %s" %
                          (state.upper(), validator.__name__, e))

    print "\n\nVALIDATION RESULTS"
    print "Passed: %s" % len(passed)
    print "Failed: %s" % len(failed)
    for fail in failed:
        print "\t%s" % fail
    print
