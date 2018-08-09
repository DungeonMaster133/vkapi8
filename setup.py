from setuptools import setup, find_packages

setup(
    name='vkapi8',
    version='1.3',
    description='Optimized vk api lib',
    url='http://github.com/ChickenLover/vkapi8',
    author='ChickenLover',
    author_email='romangg81@gmail.com',
    install_requires=[
        'requests'
    ],
    packages=find_packages()
    )

