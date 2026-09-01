"""CANARY-empty fixture.

Contains no test functions on purpose. pytest exits 5 ("no tests collected")
against this file. Exit 5 is what a deleted or renamed fixture looks like,
and it must resolve to ERROR -- never to FAIL ("the defect still
reproduces") and never to PASS. Booking exit 5 as either would manufacture
evidence about a test that never ran.

Do not add a test function to this file.
"""

CANARY_EMPTY_COLLECTS_NOTHING = True


def helper_not_a_test():
    return CANARY_EMPTY_COLLECTS_NOTHING
