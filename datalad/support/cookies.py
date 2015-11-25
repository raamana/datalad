# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Management of cookies for HTTP sessions"""

import atexit
import shelve
import appdirs
import os.path
from .network import get_tld

# FIXME should make into a decorator so that it closes the cookie_db upon exiting whatever func uses it
class CookiesDB(object):
    """Some little helper to deal with cookies

    Lazy loading from the shelved dictionary

    TODO: this is not multiprocess or multi-thread safe implementation due to shelve auto saving etc
    """
    def __init__(self, filename=None):
        self._filename = filename
        self._cookies_db = None

    def _load(self):
        if self._cookies_db is not None:
            return
        if self._filename:
            filename = self._filename
            cookies_dir = os.path.dirname(filename)
        else:
            cookies_dir = os.path.join(appdirs.user_config_dir(), 'datalad')  # FIXME prolly shouldn't hardcode 'datalad'
            filename = os.path.join(cookies_dir, 'cookies.db')

        # TODO: guarantee restricted permissions

        if not os.path.exists(cookies_dir):
            os.makedirs(cookies_dir)

        db = self._cookies_db = shelve.open(filename, writeback=True)
        atexit.register(lambda : db.close())

    def _get_provider(self, url):
        if self._cookies_db is None:
            self._load()
        return get_tld(url)

    def __getitem__(self, url):
        return self._cookies_db[self._get_provider(url)]

    def __setitem__(self, url, value):
        self._cookies_db[self._get_provider(url)] = value

    def __contains__(self, url):
        return self._get_provider(url) in self._cookies_db


# TODO -- convert into singleton pattern for CookiesDB
cookies_db = CookiesDB()
