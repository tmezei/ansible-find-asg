#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2015 Riccardo Freixo
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

"""
Ansible module for finding EC2 Auto Scaling Groups based on tags.
"""

DOCUMENTATION = '''
---
module: ec2_find_asg
version_added: "1.8"
short_description: Find AutoScalingGroups based on ec2 tags.
description:
    - Finds and retrieves properties about AutoScalingGroups based on tags.
author: Riccardo Freixo
options:
  region:
    description:
      - The AWS region to use. If not specified then the value of the EC2_REGION environment variable, if any, is used.
    required: false
    aliases: ['aws_region', 'ec2_region']
  tags:
    description:
      - dictonary of key value tags to search for.
    required: true
    default: null
    aliases: []

extends_documentation_fragment: aws
'''

EXAMPLES = '''
# a playbook task line:
- ec2_find_asg:
    region: us-west-1
    tags:
      foo: true
      bar: true
'''

import sys

from ansible.module_utils.basic import *
from ansible.module_utils.ec2 import *

try:
    import boto.ec2.autoscale
except ImportError:
    print "failed=True msg='boto required for this module'"
    sys.exit(1)

ASG_ATTRIBUTES = ('availability_zones', 'default_cooldown', 'desired_capacity',
                  'health_check_period', 'health_check_type',
                  'launch_config_name', 'load_balancers', 'max_size',
                  'min_size', 'name', 'placement_group',
                  'termination_policies', 'vpc_zone_identifier')


def get_properties(autoscaling_group):
    """
    Returns a dictionary with properties from an Auto Scaling Group.

    :type autoscaling_group: :class:`boto.ec2.autoscale.AutoScalingGroup`
    :param autoscaling_group: an Auto Scaling Group.

    :rtype: dict
    :return: a dict with an Auto Scaling Group's properties.
    """

    properties = dict((attr, getattr(autoscaling_group, attr)) for attr in ASG_ATTRIBUTES)
    properties['healthy_instances'] = 0
    properties['in_service_instances'] = 0
    properties['unhealthy_instances'] = 0
    properties['pending_instances'] = 0
    properties['viable_instances'] = 0
    properties['terminating_instances'] = 0

    if autoscaling_group.instances:
        properties['instances'] = [i.instance_id for i in autoscaling_group.instances]
        instance_facts = {}
        for i in autoscaling_group.instances:
            instance_facts[i.instance_id] = {'health_status': i.health_status,
                                             'lifecycle_state': i.lifecycle_state,
                                             'launch_config_name': i.launch_config_name}
            if i.health_status == 'Healthy' and i.lifecycle_state == 'InService':
                properties['viable_instances'] += 1
            if i.health_status == 'Healthy':
                properties['healthy_instances'] += 1
            else:
                properties['unhealthy_instances'] += 1
            if i.lifecycle_state == 'InService':
                properties['in_service_instances'] += 1
            if i.lifecycle_state == 'Terminating':
                properties['terminating_instances'] += 1
            if i.lifecycle_state == 'Pending':
                properties['pending_instances'] += 1
        properties['instance_facts'] = instance_facts
    properties['load_balancers'] = autoscaling_group.load_balancers

    if getattr(autoscaling_group, "tags", None):
        properties['tags'] = dict((t.key, t.value) for t in autoscaling_group.tags)

    return properties


def match(as_groups, search_tags):
    """
    Matches a list of as_groups against search_tags and returns a dictionary
    with a list of matching as_groups and their properties.

    :type as_groups: list of :class:`boto.ec2.autoscale.group.AutoScalingGroup`
    :param as_groups: list of Auto Scaling Groups.

    :type search_tags: dict
    :param search_tags: dict of key value pairs representing search tags.

    :rtype: dict
    :return: A dictionary of matching Auto Scaling Groups.
    """
    matching_as_groups = {}
    matching_as_groups_list = []

    for as_group in as_groups:
        as_group_tags = dict((t.key, t.value) for t in as_group.tags)
        tags_intersection = dict(set.intersection(*(set(d.iteritems()) for d in [as_group_tags, search_tags])))
        if tags_intersection == search_tags:
            matching_as_groups_list.append(get_properties(as_group))

    matching_as_groups.update(
        as_groups=matching_as_groups_list
    )

    return matching_as_groups


def find(connection, search_tags):
    """
    Fetch all Auto Scaling Groups from a region and search for groups
    with matching search_tags.

    :type connection: :class:`boto.ec2.autoscale.AutoScaleConnection`
    :param connection: A connection to Amazon's Auto Scaling Service

    :type search_tags: dict
    :param search_tags: dict of key value pairs representing search tags.

    :rtype: dict
    :return: A dictionary of matching Auto Scaling Groups.
    """
    as_groups = connection.get_all_groups()

    return match(as_groups, search_tags)


def main():
    """Main function"""
    argument_spec = ec2_argument_spec()
    argument_spec.update(
        dict(
            tags=dict(type='dict')
        ),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True
    )

    region, ec2_url, aws_connect_params = get_aws_connection_info(module)
    try:
        connection = connect_to_aws(boto.ec2.autoscale, region, **aws_connect_params)
        if not connection:
            module.fail_json(msg="failed to connect to AWS for the given region: %s" % str(region))
    except boto.exception.NoAuthHandlerFound, error:
        module.fail_json(msg=str(error))

    search_tags = module.params.get('tags')
    find(connection, search_tags)
    # module.exit_json(changed=False, **find(connection, search_tags))

if __name__ == "__main__":
    main()
