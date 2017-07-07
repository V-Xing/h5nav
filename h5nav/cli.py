#!/usr/bin/env python
"""
h5nav.py

interactive navigation of an hdf5 file

Created Jan 2017 by C. Lapeyre (corentin.lapeyre@gmail.com)
"""

import os
import sys
import cmd
from os.path import splitext, isfile
from textwrap import dedent

import numpy as np
from h5py import File

__version__ = "0.1.0"


class ExitCmd(cmd.Cmd, object):
    def can_exit(self):
        """This can be changed if exit must be protected"""
        return True

    def onecmd(self, line):
        r = super(ExitCmd, self).onecmd(line)
        if r and (self.can_exit() or
                  raw_input('exit anyway ? (yes/no):') == 'yes'):
            return True
        return False

    def do_exit(self, s):
        """Exit the interpreter.

        Ctrl-D shortcut, exit and quit all work
        """
        print "Bye!"
        sys.exit(0)
        return True
    do_EOF = do_exit
    do_quit = do_exit
    do_bye = do_exit

    def help_exit(self):
        print "Get out of here"
    help_EOF = help_exit
    help_quit = help_exit
    help_bye = help_exit


class ShellCmd(cmd.Cmd, object):
    def do_shell(self, s):
        """Execute a regular shell command"""
        os.system(s)

    def help_shell(self):
        print dedent("""\
                Execute a regular shell command.
                Useful for e.g. 'shell ls' (to see what has been written).
                Note : '!ls' is equivalent to 'shell ls'.
                Warning : Your .bashrc file is *not* sourced.""")


class SmartCmd(cmd.Cmd, object):
    """Good featured command line

    - function / help shortcuts (as short as disambiguation permits)
    - catch ^C
    - catch assertion errors
    """
    def cmdloop_with_keyboard_interrupt(self):
        doQuit = False
        while not doQuit:
            try:
                self.cmdloop()
                doQuit = True
            except KeyboardInterrupt:
                self.intro = None
                sys.stdout.write('\n')

    def default(self, line):
        """Override this command from cmd.Cmd to accept shorcuts"""
        cmd, arg, _ = self.parseline(line)
        func = [getattr(self, n) for n in self.get_names()
                if n.startswith('do_' + cmd)]
        if len(func) == 0:
            self.stdout.write('*** Unknown syntax: %s\n' % line)
            return
        elif len(func) > 1:
            print '*** {} is a shorcut to several commands'.format(cmd)
            print '    Please give more charaters for disambiguation'
            return
        else:
            func[0](arg)

    def do_help(self, arg):
        """Wrapper for cmd.Cmd.do_help to accept shortcuts"""
        if arg:
            helper = [n[5:] for n in self.get_names()
                      if n.startswith('help_' + arg)]
            if len(helper) == 0:
                self.stdout.write('*** Unknown command: %s\n' % arg)
                return
            elif len(helper) > 1:
                self.stdout.write((
                    "*** {} is a shorcut to several commands\n"
                    "     Please give more characters for disambiguation"
                    ).format(cmd))
                return
            else:
                arg = helper[0]
        cmd.Cmd.do_help(self, arg)

    def onecmd(self, line):
        """Wrapper for cmd.Cmd.onecmd to catch assertion errors"""
        try:
            cmd.Cmd.onecmd(self, line)
        except AssertionError as err:
            print "\n".join("*** " + l for l in err.message.split('\n'))


class H5NavCmd(ExitCmd, ShellCmd, SmartCmd, cmd.Cmd, object):
    """Command line interpreter for h5nav"""
    intro = dedent("""\
            Welcome to the h5nav command line (V {})
            Type help or ? for a list of commands,
                 ?about for more on this app""").format(__version__)

    path = '(no file)'
    h5file = None
    position = "/"
    last_pos = "/"

    @property
    def prompt(self):
        return "\033[92mh5nav\033[0m {0}{1} > ".format(self.path,
                                                       self.position)

    def precmd(self, line):
        """Reprint the line to know what is executed"""
        # print "\n >>> executing: ", line
        return line

    def help_about(self):
        print dedent("""
            Welcome to the h5nav app!

            With this app, you can navigate a .h5 file as if you were in
            the command line. Use `cd`, `ls`, etc... to this end.
            Information about the various fields can be given using `stats`,
            `pdf` or `dump` for example.
            """)

    def emptyline(self):
        """Empty line behavior: do nothing"""
        pass

    def do_open(self, s):
        assert len(s.split()) == 1, "invalid number of arguments"
        assert isfile(s), "Can't access file " + s
        self.path = s
        self.h5file = File(s, 'r')
        self.position = '/'

    def complete_open(self, text, line, begidx, endidx):
        candidates = [f for f in os.listdir('.')
                      if splitext(f)[1][1:] in ["h5", "hdf", "cgns"]]
        return [f for f in candidates if f.startswith(text)]

    def help_open(self):
        print "Load an hdf5 file"

    @property
    def groups(self):
        return [f for f in self.h5file[self.position].keys()
                if self.h5file[self.position + f].__class__.__name__ == "Group"]

    @property
    def datasets(self):
        return [f for f in self.h5file[self.position].keys()
                if self.h5file[self.position + f].__class__.__name__ == "Dataset"]

    def do_ls(self, s):
        """sh-like ls (degraded)

        Supports fake globbing: either 'group_name' or '*' -> all folders
        """
        if self.h5file is None:
            print "*** please open a file"
            return

        def ls_grp(grp):
            save = self.position[:]
            save_last = self.last_pos[:]
            print grp + "/"
            self.do_cd(grp)
            print "    ",
            self.do_ls('')
            self.do_cd('..')
            self.position = save[:]
            self.last_pos = save_last[:]

        if '*' in s:
            for grp in self.groups:
                ls_grp(grp)
            print "./"
            print "    " + " ".join(self.datasets)
        elif s:
            try:
                grp = self.get_whitespace_name(s)
            except UnknownLabelError:
                return
            ls_grp(grp)
        else:
            out = [g + '/' for g in self.groups] + self.datasets
            print " ".join(sorted(out))

    def help_ls(self):
        print "List current group contents. Supports `ls *`"

    def do_cd(self, s):
        """sh-like cd (degraded)

        Supports cd -, cd ..(/.. etc), no arg (back to root)
        and of course cd group
        """
        if self.h5file is None:
            print "*** please open a file"
            return
        if len(s.split()) > 1:
            print "*** invalid number of arguments"
            return
        if s == '':
            self.last_pos = self.position[:]
            self.position = '/'
        elif s == '-':
            tmp = self.last_pos[:]
            self.last_pos = self.position[:]
            self.position = tmp[:]
        elif s[:2] == '..':
            nb_up = s.count('..')
            pos = self.position.strip('/').split('/')
            if nb_up >= len(pos):
                self.last_pos = self.position[:]
                self.position = '/'
            else:
                self.last_pos = self.position[:]
                self.position = '/' + '/'.join(pos[:len(pos) - nb_up]) + '/'
        else:
            try:
                pos = self.get_whitespace_name(s).strip('/')
            except UnknownLabelError:
                return
            if pos not in self.groups:
                print "*** can only cd into groups"
                return
            self.position += pos + '/'
            self.last_pos = self.position[:]

    def complete_cd(self, text, line, begidx, endidx):
        return [f for f in self.groups if f.startswith(text)]

    def help_cd(self):
        print "Enter group. Also ok: `cd ..` (up), `cd -` (last), `cd` (root)"

    def do_print(self, s):
        """Print a dataset on screen"""
        if self.h5file is None:
            print "*** please open a file"
            return
        if len(s.split()) != 1:
            print "*** invalid number of arguments"
            return
        if s == '*':
            for dts in self.datasets:
                print dts + ' :'
                print '    ', self.get_elem(dts).value
        else:
            try:
                print self.get_elem(s).value
            except UnknownLabelError:
                return

    def complete_print(self, text, line, begidx, endidx):
        return [f for f in [s.strip() for s in self.datasets]
                if f.startswith(text)]

    def help_print(self):
        print "Print dataset to screen"

    def do_stats(self, s):
        """Print statistics for dataset on screen"""
        if self.h5file is None:
            print "*** please open a file"
            return
        if len(s.split()) != 1:
            print "*** invalid number of arguments"
            return

        def print_stats(nparr):
            try:
                mini = nparr.min()
                mean = nparr.mean()
                maxi = nparr.max()
                std = nparr.std()
            except:
                mini, mean, maxi, std = ["Undef"]*4
            print nparr.shape, nparr.dtype, mini, mean, maxi, std
        if s == '*':
            print "    Shape type min mean max std"
            for dts in self.datasets:
                print dts + ' :'
                print '    ',
                print_stats(self.get_elem(dts).value)
        else:
            try:
                nparr = self.get_elem(s).value
            except UnknownLabelError:
                return
            print "Shape type min mean max std"
            print_stats(nparr)

    def complete_stats(self, text, line, begidx, endidx):
        return [f for f in [s.strip() for s in self.datasets]
                if f.startswith(text)]

    def help_stats(self):
        print "Get general statistics of dataset"

    def do_pdf(self, s):
        """Print pdf for dataset on screen"""
        if self.h5file is None:
            print "*** please open a file"
            return
        if len(s.split()) != 1:
            print "*** invalid number of arguments"
            return
        if s == '*':
            print "    Min        Max        | Pdf (10 buckets)"
            for dts in self.datasets:
                print dts + ' :'
                dts = self.get_elem(dts).value
                print "    {0:5.4e} {1:5.4e} |".format(dts.min(), dts.max()),
                print np.histogram(dts)[0].tolist()
        else:
            try:
                nparr = self.get_elem(s).value
            except UnknownLabelError:
                return
            print "Min        Max        | Pdf (10 buckets)"
            print "{0:5.4e} {1:5.4e} |".format(nparr.min(), nparr.max()),
            print np.histogram(nparr)[0].tolist()

    def complete_pdf(self, text, line, begidx, endidx):
        return [f for f in [s.strip() for s in self.datasets]
                if f.startswith(text)]

    def help_pdf(self):
        print "Get pdf of dataset"

    def do_dump(self, s):
        """Dump dataset in numpy binary format"""
        if self.h5file is None:
            print "*** please open a file"
            return
        if len(s.split()) != 1:
            print "*** invalid number of arguments"
            return
        if s == '*':
            for dts in self.datasets:
                dts = self.get_elem(dts).value
                np.save(s, dts)
                print "--- file saved to {}.npy".format(s)
        else:
            try:
                nparr = self.get_elem(s).value
            except UnknownLabelError:
                return
            np.save(s, nparr)
            print "--- file saved to {}.npy".format(s)

    def complete_dump(self, text, line, begidx, endidx):
        return [f for f in [s.strip() for s in self.datasets]
                if f.startswith(text)]

    def help_dump(self):
        print "Dump dataset to numpy binary"

    def do_txt_dump(self, s):
        """Dump dataset in txt format"""
        if self.h5file is None:
            print "*** please open a file"
            return
        if len(s.split()) != 1:
            print "*** invalid number of arguments"
            return
        if s == '*':
            for dts in self.datasets:
                dts = self.get_elem(dts).value
                np.savetxt(s+'.txt', dts)
                print "--- file saved to {}.txt".format(s)
        else:
            try:
                nparr = self.get_elem(s).value
            except UnknownLabelError:
                return
            np.savetxt(s + '.txt', nparr)
            print "--- file saved to {}.txt".format(s)

    def complete_txt_dump(self, text, line, begidx, endidx):
        return [f for f in [s.strip() for s in self.datasets]
                if f.startswith(text)]

    def help_txt_dump(self):
        print "Dump dataset to txt file"

    def get_elem(self, name):
        return self.h5file[self.position
                           + self.get_whitespace_name(name)]

    def get_whitespace_name(self, s):
        """Wrap search for names with leading whitespace(s)"""
        targets = self.h5file[self.position].keys()
        for i in range(5):
            if s in targets:
                return s
            s = " " + s
        print "*** unknown label"
        raise UnknownLabelError


class UnknownLabelError(Exception):
    pass


def main():
    interpreter = H5NavCmd()
    if sys.argv[1:]:
        interpreter.do_open(sys.argv[1])
    interpreter.cmdloop_with_keyboard_interrupt()


if __name__ == '__main__':
    main()