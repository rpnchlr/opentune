"""Legacy pip install hook for displaying the OpenTune support message.

Modern pip installations normally install a wheel and may not execute this
hook; the message is therefore also kept in the release metadata and shown by
the first-run update modal.
"""

from setuptools import setup
from setuptools.command.install import install


MESSAGE = (
    "Thank you for installing OpenTune! Consider supporting the creator by "
    "starring or sponsoring the project: https://github.com/rpnchlr/opentune"
)

# pip's normal PEP 517 flow builds a wheel before installing it, so there is
# no portable wheel post-install hook. Printing from setup execution keeps the
# message visible in the pip installation/build log; the legacy hook below
# covers direct setup.py installs as well.
print(f"\n{MESSAGE}\n")


class PostInstallCommand(install):
    def run(self):
        super().run()
        print(f"\n{MESSAGE}\n")


setup(cmdclass={"install": PostInstallCommand})
