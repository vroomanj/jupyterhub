from tornado import gen
from dockerspawner import DockerSpawner, SystemUserSpawner

# urllib3 complains that we're making unverified HTTPS connections to swarm,
# but this is ok because we're connecting to swarm via 127.0.0.1. I don't
# actually want swarm listening on a public port, so I don't want to connect
# to swarm via the host's FQDN, which means we can't do fully verified HTTPS
# connections. To prevent the warning from appearing over and over and over
# again, I'm just disabling it for now.
import requests
requests.packages.urllib3.disable_warnings()
import re


SIMPLE_IP_PORT = re.compile('^(?:[0-9]{1,3}\.){3}[0-9]{1,3}:\d{1,5}$')


class SwarmSpawner(SystemUserSpawner):

    container_ip = '0.0.0.0'

    @gen.coroutine
    def lookup_node_name(self):
        """Find the name of the swarm node that the container is running on."""
        containers = yield self.docker('containers', all=True)
        for container in containers:
            if container['Id'] == self.container_id:
                name, = container['Names']
                node, container_name = name.lstrip("/").split("/")
                raise gen.Return(node)

    @gen.coroutine
    def start(self, image=None, extra_create_kwargs=None, extra_host_config=None):
        # look up mapping of node names to ip addresses
        info = yield self.docker('info')
        self.node_info = {}
        for node, nodeip in [(entry[0], entry[1].split(":")[0])
                             for entry in info['DriverStatus']
                             if SIMPLE_IP_PORT.match(entry[1])]:
            self.node_info[node] = nodeip
        self.log.debug("Swarm nodes are: {}".format(self.node_info))

        # specify extra host configuration
        if extra_host_config is None:
            extra_host_config = {}
        if 'mem_limit' not in extra_host_config:
            extra_host_config['mem_limit'] = '1g'

        # specify extra creation options
        if extra_create_kwargs is None:
            extra_create_kwargs = {}
        if 'working_dir' not in extra_create_kwargs:
            extra_create_kwargs['working_dir'] = self.homedir

        # start the container
        yield DockerSpawner.start(
            self, image=image,
            extra_create_kwargs=extra_create_kwargs,
            extra_host_config=extra_host_config)

        # figure out what the node is and then get its ip
        name = yield self.lookup_node_name()
        self.user.server.ip = self.node_info[name]
        self.log.info("{} was started on {} ({}:{})".format(
            self.container_name, name, self.user.server.ip, self.user.server.port))

        self.log.info(self.env)
