#!/bin/bash
export WORKSPACE=$1
. $WORKSPACE/env_vars.sh
env
export DIR=$WORKSPACE/jenkins_setup/scripts/graphicTest/chroot

$DIR/setupSources.bash &&
$DIR/installNvidia.bash &&
$DIR/installLatestRosRepos.bash &&
$DIR/installSimulator.bash &&
$DIR/installTest.bash &&
$DIR/startTest.bash

rosrun rosunit clean_junit_xml.py
