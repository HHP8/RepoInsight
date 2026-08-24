# Link escape fixture

The security test creates a symlink named `outside-link.py` in this directory that targets a temporary sentinel outside the fixture root. Symlinks are created at test time because Git and Windows checkouts do not portably preserve them.
