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
    url='https://github.com/wagnerflo/yamap',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3 :: Only',
    ],
    license_files=['LICENSE'],
    python_requires='>= 3.8',
    install_requires=[
        'APScheduler >= 3.0, < 4.0',
        'noblklog',
        'psutil',
    ],
    packages=['chaqum'],
    entry_points = {
        'console_scripts': [
            'chaqum=chaqum.cmdline:main',
        ],
    },
)
