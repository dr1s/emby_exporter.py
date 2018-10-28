from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='emby_exporter',
    version='0.1.2',
    url='https://github.com/dr1s/emby_exporter.py',
    author='dr1s',
    license='MIT',
    description='Export emby metrics for prometheus',
    long_description=long_description,
    long_description_content_type="text/markdown",
    install_requires=['prometheus_client', 'embypy'],
    packages=find_packages(),
    include_package_data=True,
    entry_points={
        'console_scripts': ['emby_exporter=emby_exporter.emby_exporter:main']
    },
)
