#!/usr/bin/env python
"""Django command runner that always uses the isolated local database."""

import os
import sys


def main():
    os.environ['DJANGO_SETTINGS_MODULE'] = 'dental_clinic.settings_local'
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
