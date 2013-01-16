#!/usr/bin/env python

import urllib2
import yaml

from jenkins_setup import cob_common


class Cob_Distro(object):
    """
    TODO
    """

    def __init__(self, name, url=None):
        """
        TODO
        """

        self.repositories = {}

        if url:
            self.url = url
            self.release_file = urllib2.urlopen(self.url)
            self.repos_dict = yaml.load(self.release_file.read())['repositories']
        else:
            self.url = 'https://raw.github.com/fmw-jk/jenkins_setup/master/releases/cob_%s.yaml' % name  # TODO change to ipa320
            self.release_file = urllib2.urlopen(self.url)
            self.repos_dict = yaml.load(self.release_file.read())['repositories']

        for repo_name, data in self.repos_dict.iteritems():
            repo = Cob_Distro_Repo(repo_name, data)
            self.repositories[repo_name] = repo


class Cob_Distro_Pipe(object):
    """
    TODO
    """

    def load_from_dict(self, repos_dict):
        """
        TODO
        """

        self.repositories = {}
        self.repos_dict = repos_dict

        for repo_name, data in self.repos_dict.iteritems():
            repo = Cob_Distro_Pipe_Repo(repo_name, data)
            self.repositories[repo_name] = repo

    def load_from_url(self, server_name, user_name):
        buildpipe_conf_dict = cob_common.get_buildpipeline_configs(server_name, user_name)
        self.load_from_dict(buildpipe_conf_dict['repositories'])

    def get_custom_dependencies(self):
        """
        Get a :dict: with dependencies and corresponding repository.

        :returns: return :dict: with dependencies as keys and the corresponding
        repositories (in a list) as value, ``dict``
        """

        #deps = {dep: repo for dep, repo in self.repositories[repo].dependencies.keys()
                #for repo in self.repositories.keys()}

        deps = {}
        for repo in self.repositories.keys():
            for dep in self.repositories[repo].dependencies.keys():
                if dep in deps:
                    deps[dep].append(repo)
                else:
                    deps[dep] = [repo]

        return deps


class Cob_Distro_Repo(object):
    """
    Object containing repository information
    """
    def __init__(self, name, data):
        """
        :param name: repository name, ``str``
        :param data: repository information, e.g. from a rosdistro file, ``dict``
        """

        self.name = name
        self.type = data['type']
        self.url = data['url']
        self.version = None
        if 'version' in data:
            self.version = data['version']

        self.poll = None
        if 'poll' in data:
            self.poll = data['poll']

    def get_rosinstall(self):
        """
        Generate a rosinstall file entry with the stored information.

        :returns: return rosinstall file entry, ``str``
        """

        if self.version:
            return yaml.dump([{self.type: {'local-name': self.name,
                                           'uri': '%s' % self.url,
                                           'version': '%s' % self.version}}],
                             default_style=False)
        else:
            return yaml.dump([{self.type: {'local-name': self.name,
                                           'uri': '%s' % self.url}}],
                             default_style=False)


class Cob_Distro_Pipe_Repo(Cob_Distro_Repo):
    """
    Object containing repository information and additional information for
    the buildpipeline
    """
    def __init__(self, name, data):
        """
        :param name: repository name, ``str``
        :param data: repository and dependency information from pipeline_config
        file, ``dict``
        """

        super(Cob_Distro_Pipe_Repo, self).__init__(name, data)

        self.poll = True  # first level repos are always polled
        self.ros_distro = data['ros_distro']
        self.prio_ubuntu_distro = data['prio_ubuntu_distro']
        self.prio_arch = data['prio_arch']

        if data['matrix_distro_arch']:
            self.matrix_distro_arch = data['matrix_distro_arch']  # TODO ??

        self.dependencies = None
        if data['dependencies']:
            self.dependencies = {}
            for dep_name, dep_data in data['dependencies'].iteritems():
                dep = Cob_Distro_Repo(dep_name, dep_data)
                self.dependencies[dep_name] = dep
            #self.dependencies = Cob_Distro('deps', repos_dict=data['dependencies'])

        if data['jobs']:
            self.jobs = data['jobs']
