from setuptools import setup, find_packages

setup(
    name='emby_exporter',
    version='0.1.dev0',
    url='https://github.com/dr1s/emby_exporter.py',
    author='dr1s',
    license='MIT',
    description='Export emby metrics for prometheus',
    install_requires=['prometheus_client', 'embypy'],
    packages=find_packages(),
    include_package_data = True,
    entry_points={'console_scripts': ['emby_exporter=emby_exporter.emby_exporter:main']},
)
