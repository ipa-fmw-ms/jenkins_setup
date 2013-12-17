#!/usr/bin/env python

import optparse
import sys
import os
import shutil
import datetime
import traceback

from jenkins_setup import common, rosdep, cob_pipe

def main():
    #########################
    ### parsing arguments ###
    #########################
    time_parsing = datetime.datetime.now()
    print "=====> entering argument parsing step at", time_parsing

    # parse parameter values
    parser = optparse.OptionParser()
    parser.add_option('-v', '--verbose', action='store_true', default=False)
    (options, args) = parser.parse_args()

    if len(args) < 5:
        print "Usage: %s pipeline_repos_owner server_name user_name ros_distro build_repo" % sys.argv[0]
        raise common.BuildException("Wrong arguments for build script")

    # get arguments
    pipeline_repos_owner = args[0]
    server_name = args[1]
    user_name = args[2]
    ros_distro = args[3]
    build_identifier = args[4]                      # repository + suffix
    build_repo = build_identifier.split('__')[0]    # only repository to build
    # environment variables
    workspace = os.environ['WORKSPACE']
    ros_package_path = os.environ['ROS_PACKAGE_PATH']

    # cob_pipe object
    print "LIST:" + str(cob_pipe.CobPipe()) +"REPOOWN:" + str(pipeline_repos_owner)+ "SERVER:" + str(server_name) + "USER:" + str(user_name)
    cp_instance = cob_pipe.CobPipe()
    cp_instance.load_config_from_url(pipeline_repos_owner, server_name, user_name)
    pipe_repos = cp_instance.repositories
    common.output("Pipeline configuration successfully loaded", blankline='b')

    # (debug) output
    print "\n", 50 * 'X'
    print "\nTesting on ros distro:  %s" % ros_distro
    print "Testing repository: %s" % build_repo
    if build_repo != build_identifier:
        print "       with suffix: %s" % build_identifier.split('__')[1]
    print "Using source: %s" % pipe_repos[build_identifier].url
    print "Testing branch/version: %s" % pipe_repos[build_identifier].version
    print "\n", 50 * 'X'

    #remove old and create new folder
    #while len(os.listdir(workspace)) >= 7:
    #    list = os.listdir(workspace)
    #    shutil.rmtree(workspace + "/" + sorted(list)[0]) #with common.call rm -rf later        
    #workspace = workspace + '/' + str(datetime.datetime.now())
    #print str(workspace)


    # set up directories variables
    tmpdir = os.path.join(workspace, 'test_repositories') #TODO check for old versions (delete oldest) and create new directory with timestamp
    common.call("rm -rf " + tmpdir)
    repo_sourcespace = os.path.join(tmpdir, 'src_repository')                      # location to store repositories in
    repo_sourcespace_wet = os.path.join(tmpdir, 'src_repository', 'wet', 'src')    # wet (catkin) repositories
    repo_sourcespace_dry = os.path.join(tmpdir, 'src_repository', 'dry')           # dry (rosbuild) repositories
    repo_static_analysis_results = os.path.join(tmpdir, 'src_repository', 'static_analysis_results') # location for static code test results
    repo_buildspace = os.path.join(tmpdir, 'build_repository')                     # location for build output
    dry_build_logs = os.path.join(repo_sourcespace_dry, 'build_logs')              # location for build logs

    ################
    ### checkout ###
    ################
    time_checkout = datetime.datetime.now()
    print "=====> entering checkout step at", time_checkout

    # download build_repo from source #
    print "Creating rosinstall file for repository %s" % build_repo
    rosinstall = ""
    if build_identifier in pipe_repos:  # check if triggering identifier is really present in pipeline config
        rosinstall += pipe_repos[build_identifier].get_rosinstall()
        rosinstall += "- other: {local-name: /u/robot}" #TODO: not hardcoding (with multiple directories?)
    else:
        err_msg = "Pipeline was triggered by repository %s which is not in pipeline config!" % build_identifier
        raise common.BuildException(err_msg)

    # write rosinstall file
    print "Rosinstall file for repository: \n %s" % rosinstall
    with open(os.path.join(workspace, 'repo.rosinstall'), 'w') as f:
        f.write(rosinstall)
    print "Install repository from source:"
    # create repo sourcespace directory 'src_repository'
    os.makedirs(repo_sourcespace)
    # rosinstall repos
    common.call("rosinstall -j 8 --verbose --continue-on-error %s %s/repo.rosinstall /opt/ros/%s"
                % (repo_sourcespace, workspace, ros_distro))

    # get the repositories build dependencies
    print "Get build dependencies of repo"

    # get all packages in sourcespace
    (catkin_packages, stacks, manifest_packages) = common.get_all_packages(repo_sourcespace)
    if ros_distro == 'electric' and catkin_packages != {}:
        raise common.BuildException("Found wet packages while building in ros electric")

    # (debug) output
    if options.verbose:
        print "Packages in %s:" % repo_sourcespace
        print "Catkin: ", catkin_packages
        print "Rosbuild:\n  Stacks: ", stacks
        print "  Packages: ", manifest_packages

        # get deps directly for catkin (like in willow code)
        try:
            print "Found wet build dependencies:\n%s" % '- ' + '\n- '.join(sorted(common.get_dependencies(repo_sourcespace, build_depends=True, test_depends=False)))
        except:
            pass
        # deps catkin
        repo_build_dependencies = common.get_nonlocal_dependencies(catkin_packages, {}, {}, build_depends=True, test_depends=False)
        print "Found wet dependencies:\n%s" % '- ' + '\n- '.join(sorted(repo_build_dependencies))
        # deps stacks
        repo_build_dependencies = common.get_nonlocal_dependencies({}, stacks, {})
        print "Found dry dependencies:\n%s" % '- ' + '\n- '.join(sorted(repo_build_dependencies))

    # check if build_repo is wet or dry and get all corresponding deps
    build_repo_type = ''
    if build_repo in catkin_packages:
        print "repo %s is wet" % build_repo
        build_repo_type = 'wet'
        repo_build_dependencies = common.get_nonlocal_dependencies(catkin_packages, {}, {}, build_depends=True, test_depends=False)
    elif build_repo in stacks:
        print "repo %s is dry" % build_repo
        build_repo_type = 'dry'
        repo_build_dependencies = common.get_nonlocal_dependencies({}, stacks, {})
    else:
        # build_repo is neither wet nor dry
        raise common.BuildException("Repository %s to build not found in sourcespace" % build_repo)

    # install user-defined/customized dependencies of build_repo from source
    rosinstall = ''
    fulfilled_deps = []
    for dep in repo_build_dependencies:
        if dep in pipe_repos[build_identifier].dependencies:
            print "Install user-defined build dependency %s from source" % dep
            rosinstall += pipe_repos[build_identifier].dependencies[dep].get_rosinstall()
            fulfilled_deps.append(dep)

    # install additional, indirect user-defined dependencies
    for dep in pipe_repos[build_identifier].dependencies:
        if dep not in fulfilled_deps:
            print "Install additional user-defined build dependency %s from source" % dep
            rosinstall += pipe_repos[build_identifier].dependencies[dep].get_rosinstall()
            fulfilled_deps.append(dep)

    # check if all user-defined/customized dependencies are satisfied
    if sorted(fulfilled_deps) != sorted(pipe_repos[build_identifier].dependencies):
        print "Not all user-defined build dependencies are fulfilled"
        print "User-defined build dependencies:\n - %s" % '\n - '.join(pipe_repos[build_identifier].dependencies)
        print "Fulfilled dependencies:\n - %s" % '\n - '.join(fulfilled_deps)
        raise common.BuildException("Not all user-defined build dependencies are fulfilled")
    if rosinstall != '':
        # write .rosinstall file
        print "Rosinstall file for user-defined build dependencies: \n %s" % rosinstall
        rosinstall += "- other: {local-name: /u/robot}"#TODO: not hardcoding (with multiple directories?)
        with open(os.path.join(workspace, "repo.rosinstall"), 'w') as f:
            f.write(rosinstall)
        print "Install user-defined build dependencies from source"
        # rosinstall depends
        common.call("rosinstall -j 8 --verbose --continue-on-error %s %s/repo.rosinstall /opt/ros/%s"
                    % (repo_sourcespace, workspace, ros_distro))

        # get also deps of just installed user-defined/customized dependencies
        (catkin_packages, stacks, manifest_packages) = common.get_all_packages(repo_sourcespace)
        if build_repo_type == 'wet':
            if stacks != {}:
                raise common.BuildException("Catkin (wet) package %s depends on (dry) stack(s):\n%s"
                                            % (build_repo, '- ' + '\n- '.join(stacks)))
            # take only wet packages
            repo_build_dependencies = common.get_nonlocal_dependencies(catkin_packages, {}, {}, build_depends=True, test_depends=False)
        else:  # dry build repo
            # take all packages
            repo_build_dependencies = common.get_nonlocal_dependencies(catkin_packages, stacks, {}, build_depends=True, test_depends=False)
        repo_build_dependencies = [dep for dep in repo_build_dependencies if dep not in fulfilled_deps]

    # separate installed repos in wet and dry
    print "Separate installed repositories in wet and dry"
    os.makedirs(repo_sourcespace_wet)
    os.makedirs(repo_sourcespace_dry)
    # get all folders in repo_sourcespace
    sourcespace_dirs = [name for name in os.listdir(repo_sourcespace) if os.path.isdir(os.path.join(repo_sourcespace, name))]
    for dir in sourcespace_dirs:
        if dir in catkin_packages.keys():
            shutil.move(os.path.join(repo_sourcespace, dir), os.path.join(repo_sourcespace_wet, dir))
        if dir in stacks.keys():
            shutil.move(os.path.join(repo_sourcespace, dir), os.path.join(repo_sourcespace_dry, dir))
    

    ############################
    ### install dependencies ###
    ############################
    time_install = datetime.datetime.now()
    print "=====> entering dependency installation step at", time_install

    # Create rosdep object
    rosdep_resolver = None

    print "Install build dependencies: %s" % (', '.join(repo_build_dependencies))
    #common.apt_get_install_also_nonrosdep(repo_build_dependencies, ros_distro, rosdep_resolver)
    print "ASK YOUR ADMIN TO INSTALL:" + str(repo_build_dependencies)
    
    print "ASK YOUR ADMIN TO INSTALL THE PACKAGES ABOVE"
    # check which packages are installed
    # FAIL WHEN SOMETHING MISSING
    #############
    ### build ###
    #############
    time_build = datetime.datetime.now()
    print "=====> entering build step at", time_build

    # env
    print "Set up ros environment variables"
    ros_env_repo = common.get_ros_env('/opt/ros/%s/setup.bash' % ros_distro)
    if options.verbose:
        common.call("env", ros_env_repo)

    ### catkin repositories
    if catkin_packages != {}:
        # set up catkin workspace
        if ros_distro == 'fuerte':
            if 'catkin' not in catkin_packages.keys():
                # add catkin package to rosinstall
                rosinstall = "\n- git: {local-name: catkin, uri: 'git://github.com/ros/catkin.git', version: fuerte-devel}"
                print "Install catkin"
                # rosinstall catkin
                common.call("rosinstall -j 8 --verbose %s %s/repo.rosinstall /opt/ros/%s"
                            % (repo_sourcespace_wet, workspace, ros_distro))

            print "Create a CMakeLists.txt for catkin packages"
            common.call("ln -s %s %s" % (os.path.join(repo_sourcespace_wet, 'catkin', 'cmake', 'toplevel.cmake'),
                                         os.path.join(repo_sourcespace_wet, 'CMakeLists.txt')))
        else:
            common.call("catkin_init_workspace %s" % repo_sourcespace_wet, ros_env_repo)

        #os.mkdir(repo_buildspace)
        os.chdir(repo_sourcespace_wet + "/..")
        try:
            common.call("catkin_make", ros_env_repo)
        except common.BuildException as ex:
            print ex.msg
            raise common.BuildException("Failed to catkin_make wet repositories")
        
        # setup ros environment to source wet packages before building dry ones
        ros_env_repo = common.get_ros_env(os.path.join(repo_sourcespace_wet, '../devel/setup.bash'))

    ### rosbuild repositories
    if build_repo_type == 'dry':
        ros_env_repo['ROS_PACKAGE_PATH'] = ':'.join([repo_sourcespace, ros_package_path])
        if options.verbose:
            common.call("env", ros_env_repo)

        if ros_distro == 'electric':
            print "Rosdep"
            common.call("rosmake rosdep", ros_env_repo)
        for stack in stacks.keys():
            common.call("rosdep install -y %s" % stack, ros_env_repo)

        # build dry repositories
        print "Build repository %s" % build_repo
        try:
            common.call("rosmake -i -rV --skip-blacklist --profile --pjobs=8 --output=%s %s" %
                        (dry_build_logs, build_repo), ros_env_repo)
        except common.BuildException as ex:
            try:
                shutil.move(dry_build_logs, os.path.join(workspace, "build_logs"))
            finally:
                print ex.msg
                raise common.BuildException("Failed to rosmake %s" % build_repo)

    # the end (steps: parsing, checkout, install, analysis, build, finish)
    time_finish = datetime.datetime.now()
    print "=====> finished script at", time_finish
    print "durations:"
    print "parsing arguments in       ", (time_checkout - time_parsing)
    print "checkout in                ", (time_install - time_checkout)
    print "install dependencies in    ", (time_build - time_install)
    print "build in                   ", (time_finish - time_build)
    print ""
    print "For testing, please run the following line in your testing terminal"
    print "source " + repo_sourcespace + "/setup.bash"
    print ""

if __name__ == "__main__":
    # global try
    try:
        main()
        print "Build script finished cleanly!"

    # global catch
    except (common.BuildException, cob_pipe.CobPipeException) as ex:
        print traceback.format_exc()
        print "Build script failed!"
        print ex.msg
        raise ex

    except Exception as ex:
        print traceback.format_exc()
        print "Build script failed! Check out the console output above for details."
        raise ex
