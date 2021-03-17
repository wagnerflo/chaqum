from setuptools import setup
from pathlib import Path

setup(
    name='chaqum',
    description='[ˈkeɪkjuːm], the queue manager for chaotic job queues.',
    long_description=(Path(__file__).parent / 'README.md').read_text(),
    long_description_content_type='text/markdown',
    version='0.1',
    author='Florian Wagner',
    author_email='florian@wagner-flo.net',
    url='https://github.com/wagnerflo/chaqum',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 3 :: Only',
    ],
    license_files=['LICENSE'],
    python_requires='>= 3.8',
    install_requires=[
        'APScheduler >= 3.0, < 4.0',
        'noblklog >= 0.3',
        'psutil',
    ],
    packages=['chaqum'],
    entry_points = {
        'console_scripts': [
            'chaqum=chaqum.cmdline:main',
        ],
    },
    package_data={
        'chaqum': [ 'logging.*.json' ],
    }
)
