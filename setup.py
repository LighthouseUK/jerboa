from distutils.core import setup

setup(
    name='jerboa',
    packages=['jerboa'],  # this must be the same as the name above
    version='0.2.2-alpha',
    description='',
    author='Matt Badger',
    author_email='foss@lighthouseuk.net',
    url='https://github.com/LighthouseUK/jerboa',  # use the URL to the github repo
    download_url='https://github.com/LighthouseUK/jerboa/tarball/0.2.2-alpha',  # I'll explain this in a second
    keywords=['gae', 'lighthouse', 'jerboa', 'webapp2'],  # arbitrary keywords
    classifiers=[],
    requires=['webapp2', 'blinker', 'wtforms', 'jinja2', 'pytz', 'babel', 'pycrypto'],
    # tests_require=['WebTest']
)
