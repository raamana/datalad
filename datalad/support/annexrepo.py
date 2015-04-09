# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface to git-annex by Joey Hess.

For further information on git-annex see https://git-annex.branchable.com/.

"""

from os import getcwd
from os.path import join as p_join, exists, normpath, isabs, commonprefix, relpath
import logging

from ConfigParser import NoOptionError

from gitrepo import GitRepo
from datalad.cmd import Runner as Runner
from exceptions import CommandNotAvailableError, CommandError, FileNotInAnnexError, FileInGitError

lgr = logging.getLogger('datalad.annex')


class AnnexRepo(GitRepo):
    """Representation of an git-annex repository.


    Paths given to any of the class methods will be interpreted as relative to Repo's dir if they're relative paths.
    Absolute paths should also be accepted.
    """
    # TODO: Check exceptions for the latter and find a workaround. For example: git annex lookupkey doesn't accept
    # absolute paths. So, build relative paths from absolute ones and may be include checking whether or not they
    # result in a path inside the repo.
    # How to expand paths, if cwd is deeper in repo?
    # git annex proxy will need additional work regarding paths.
    def __init__(self, path, url=None, runner=None, direct=False):
        """Creates representation of git-annex repository at `path`.

        AnnexRepo is initialized by giving a path to the annex.
        If no annex exists at that location, a new one is created.
        Optionally give url to clone from.

        Parameters:
        -----------
        path: str
          path to git-annex repository

        url: str
          url to the to-be-cloned repository.
          valid git url according to http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS required.

        runner: Runner
           Provide a Runner in case AnnexRepo shall not create it's own. This is especially needed in case of
           desired dry runs.

        direct: bool
           If True, force git-annex to use direct mode
        """
        super(AnnexRepo, self).__init__(path, url)

        self.cmd_call_wrapper = runner or Runner()
        # TODO: Concept of when to set to "dry". Includes: What to do in gitrepo class?
        #       Now: setting "dry" means to give a dry-runner to constructor.
        #       => Do it similar in gitrepo/dataset. Still we need a concept of when to set it
        #       and whether this should be a single instance collecting everything or more
        #       fine grained.

        # Check whether an annex already exists at destination
        if not exists(p_join(self.path, '.git', 'annex')):
            lgr.debug('No annex found in %s. Creating a new one ...' % self.path)
            self._annex_init()

        if direct and not self.is_direct_mode():  # only force direct mode; don't force indirect mode
            self.set_direct_mode()

    def is_direct_mode(self):
        """Indicates whether or not annex is in direct mode

        Returns
        -------
        True if in direct mode, False otherwise.
        """

        try:
            dm = self.repo.config_reader().get_value("annex", "direct")
        except NoOptionError, e:
            #If .git/config lacks an entry "direct" it's actually indirect mode.
            dm = False

        return dm

    def is_crippled_fs(self):
        """Indicates whether or not git-annex considers current filesystem 'crippled'.

        Returns
        -------
        True if on crippled filesystem, False otherwise
        """

        try:
            cr_fs = self.repo.config_reader().get_value("annex", "crippledfilesystem")
        except NoOptionError, e:
            #If .git/config lacks an entry "crippledfilesystem" it's actually not crippled.
            cr_fs = False

        return cr_fs

    def set_direct_mode(self, enable_direct_mode=True):
        """Switch to direct or indirect mode

        Parameters
        ----------
        enable_direct_mode: bool
            True means switch to direct mode,
            False switches to indirect mode

        Raises
        ------
        CommandNotAvailableError
            in case you try to switch to indirect mode on a crippled filesystem
        """
        if self.is_crippled_fs() and not enable_direct_mode:
            raise CommandNotAvailableError(cmd="git-annex indirect",
                                           msg="Can't switch to indirect mode on that filesystem.")
        mode = 'direct' if enable_direct_mode else 'indirect'
        self.cmd_call_wrapper.run(['git', 'annex', mode], cwd=self.path,
                                  expect_stderr=True)
        #TODO: 1. Where to handle failure? 2. On crippled filesystem don't even try.

    def _annex_init(self):
        """Initializes an annex repository.

        Note: This is intended for private use in this class by now.
        If you have an object of this class already, there shouldn't be a need to 'init' again.

        """
        # TODO: provide git and git-annex options.
        # TODO: Document (or implement respectively) behaviour in special cases like direct mode (if it's different),
        # not existing paths, etc.

        status = self.cmd_call_wrapper.run(['git', 'annex', 'init'], cwd=self.path)
        # TODO: When to expect stderr? on crippled filesystem for example (think so)?
        if status not in [0, None]:
            lgr.error('git annex init returned status %d.' % status)


    def annex_get(self, files, **kwargs):
        """Get the actual content of files

        Parameters:
        -----------
        files: list
            list of paths to get

        kwargs: options for the git annex get command. For example `from='myremote'` translates to annex option
            "--from=myremote"
        """

        cmd_list = ['git', 'annex', 'get']

        for key in kwargs.keys():
            cmd_list.extend([" --%s=%s" % (key, kwargs.get(key))])
        #TODO: May be this should go in a decorator for use in every command.

        for path in files:
            cmd_list.append(self._check_path(path))

        #don't capture stderr, since it provides progress display
        status = self.cmd_call_wrapper.run(cmd_list, log_stdout=True, log_stderr=False, log_online=True,
                                           expect_stderr=False, cwd=self.path)

        if status not in [0, None]:
            # TODO: Actually this doesn't make sense. Runner raises exception in this case,
            # which leads to: Runner doesn't have to return it at all.
            lgr.error('git annex get returned status: %s' % status)
            raise CommandError(cmd=' '.join(cmd_list))

    def annex_add(self, files, **kwargs):
        """Add file(s) to the annex.

        Parameters
        ----------
        files: list
            list of paths to add to the annex
        """

        cmd_list = ['git', 'annex', 'add']

        for key in kwargs.keys():
            cmd_list.extend([" --%s=%s" % (key, kwargs.get(key))])
        #TODO: May be this should go in a decorator for use in every command.

        for path in files:
            cmd_list.append(self._check_path(path))

        status = self.cmd_call_wrapper.run(cmd_list, cwd=self.path)

        if status not in [0, None]:
            lgr.error("git annex add returned status: %s" % status)
            raise CommandError(cmd=' '.join(cmd_list), msg="", code=status)

    def annex_proxy(self, git_cmd):
        """Use git-annex as a proxy to git

        This is needed in case we are in direct mode, since there's no git working tree, that git can handle.

        Parameters:
        -----------
        git_cmd: str
            the actual git command

        Returns:
        --------
        output: tuple
            a tuple constisting of the lines of the output to stdout
            Note: This may change. See TODO.
        """



        cmd_str = "git annex proxy -- %s" % git_cmd
        # TODO: By now git_cmd is expected to be string. Figure out how to deal with a list here.

        if not self.is_direct_mode():
            lgr.warning("annex_proxy called in indirect mode: %s" % git_cmd)
            raise CommandNotAvailableError(cmd=cmd_str, msg="Proxy doesn't make sense if not in direct mode.")

        status, output = self.cmd_call_wrapper(cmd_str, shell=True, return_output=True)
        # TODO: For now return output for testing. This may change later on.

        if status not in [0, None]:
            lgr.error("git annex proxy returned status: %s" % status)
            raise CommandError(cmd=cmd_str, msg="", code=status)

        return output

    def get_file_key(self, path):
        """Get key of an annexed file

        Parameters:
        -----------
        path: str
            file to look up; have to be a path relative to repo's base dir

        Returns:
        --------
        str
            key used by git-annex for `path`
        """

        path = self._check_path(path)
        cmd_list = ['git', 'annex', 'lookupkey', path]

        # TODO: For now this means, path_to_file has to be a string,
        # containing a single path. In oppposition to git annex lookupkey itself,
        # which can look up several files at once.

        cmd_str = ' '.join(cmd_list)  # have a string for messages

        output = None
        try:
            status, output = self.cmd_call_wrapper.run(cmd_list, return_output=True, cwd=self.path)
        except RuntimeError, e:
            # TODO: This has to be changed, due to PR #103, anyway.
            if e.message.find("Failed to run %s" % cmd_list) > -1 and e.message.find("Exit code=1") > -1:
                # if annex command fails we don't get the status directly
                # nor does git-annex propagate IOError (file not found) or sth.
                # So, we have to find out:

                f = open(p_join(self.path, path), 'r')  # raise possible IOErrors
                f.close()

                # if we got here, the file is present and accessible, but not in the annex

                if path in self.get_indexed_files():
                    raise FileInGitError(cmd=cmd_str, msg="File not in annex, but git: %s" % path,
                                              filename=path)

                raise FileNotInAnnexError(cmd=cmd_str, msg="File not in annex: %s" % path,
                                               filename=path)

        key = output[0].split()[0]

        return key

    def file_has_content(self, path):
        """ Check whether the file `path` is present with its content.

        Parameters:
        -----------
        path: str

        """
        # TODO: Also provide option to look for key instead of path

        path = self._check_path(path)
        cmd_list = ['git', 'annex', 'find', path]

        try:
            status, output = self.cmd_call_wrapper.run(cmd_list, return_output=True, cwd=self.path)
            # TODO: Proper exception/exitcode handling after that topic is reworked in Runner-class
        except RuntimeError, e:
            status = 1

        if status not in [0, None] or output[0] == '':
            is_present = False
        else:
            is_present = output[0].split()[0] == path

        return is_present

    def _check_path(self, path):
        """Helper to check paths passed to methods of this class.

        TODO: This may go into a decorator or sth. like that and then should work on a list.
        But: Think about behaviour if only some of the list's items are invalid.

        Checks whether `path` is inside repository and normalize it. Additionally paths are converted into
        relative paths with respect to AnnexRepo's base dir, considering os.getcwd() in case of relative paths.

        Returns:
        --------
        str:
            normalized path, that is a relative path with respect to `self.path`
        """
        path = normpath(path)
        if isabs(path):
            if commonprefix([path, self.path]) != self.path:
                raise FileNotInAnnexError(msg="Path outside repository: %s" % path, filename=path)
            else:
                pass

        elif commonprefix([getcwd(), self.path]) == self.path:
            # If we are inside repository, rebuilt relative paths.
            path = p_join(getcwd(), path)
        else:
            # We were called from outside the repo. Therefore relative paths
            # are interpreted as being relative to self.path already.
            return path

        return relpath(path, start=self.path)