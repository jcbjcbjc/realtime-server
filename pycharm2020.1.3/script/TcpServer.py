from __future__ import annotations
import asyncio
import functools
# import json
# import random
import signal
import platform
import sys
# from random import random
import socket

# from PuppetBindEntity import PuppetBindEntity
# from battle_entity.Puppet import Puppet
# from core.common import MsgpackSupport
from asyncio import events

import typing

# from core.util.performance.cpu_load_handler import CpuLoad

if typing.TYPE_CHECKING:
    from RpcHandler import RpcHandler

from TcpConn import TcpConn
from common import gv
from core.EtcdSupport import ServiceNode
# from core.common import EntityScanner
# from core.common.EntityFactory import EntityFactory
from core.mobilelog.LogManager import LogManager
from core.util import EnhancedJson
from core.util.TimerHub import TimerHub
from util.SingletonEntityManager import SingletonEntityManager
from common import gv
from core.common import EntityScanner
from core.common.EntityFactory import EntityFactory
from core.tool import incremental_reload
# from core.tool import incremental_reload

# TCP_SERVER = None


class TcpServer(object):

    def __init__(self, server_name, json_conf_path):
        self._ev_loop = events.new_event_loop()
        events.set_event_loop(self._ev_loop)

        self._timer_hub = TimerHub()

        self._addr_2_conn_map = {}
        self._etcd_service_node = None
        # self.register_entities()

        self.parse_json_conf(json_conf_path)
        gv.game_server_name = server_name

        LogManager.set_log_tag(gv.game_server_name)
        LogManager.set_log_path(gv.game_json_conf["log_path"])
        self._logger = LogManager.get_logger()

        gv.add_server_singleton(self)

        self._register_server_entities()
        # self.register_battle_entities()
        self._register_component()

        incremental_reload.init_reload_record()  # 注意!! 一定要放到EntityScanner注册了的代码之后, 不然sys.modules里没相关的模块

    def _register_component(self):
        from common.component.Component import Component
        from common.component import ComponentRegister
        # gameconfig = self.config[self.config_sections.game]
        component_root = gv.game_json_conf.get('component_root')
        if component_root is None:
            self._logger.error('conf file has no component_root!')
            return
        component_classes = EntityScanner.scan_entity_package(component_root, Component)
        component_classes = component_classes.items()
        # component_classes.sort(lambda a, b: cmp(a[0], b[0]))
        for comp_type, comp_cls in component_classes:
            ComponentRegister.register(comp_cls)

    # def register_battle_entities(self):
    #     from BattleEntity import BattleEntity
    #     _ber = gr.game_json_conf.get('battle_entity_root', None)
    #     if _ber is None:
    #         self.logger.error('conf file has no battle_entity_root!')
    #         return
    #     entity_classes = EntityScanner.scan_entity_package(_ber, BattleEntity)
    #     entity_classes = entity_classes.items()
    #
    #     # def cmp(x, y):
    #     #     if x < y:
    #     #         return -1
    #     #     elif x == y:
    #     #         return 0
    #     #     else:
    #     #         return 1
    #     #
    #     # entity_classes.sort(lambda a, b: cmp(a[0], b[0]))
    #     for cls_name, cls in entity_classes:
    #         EntityFactory.instance().register_entity(cls_name, cls)

    @staticmethod
    def _register_server_entities():
        from BattleEntity import BattleEntity
        from LobbyEntity import LobbyEntity
        from server_entity.ServerEntity import ServerEntity
        _ser = gv.game_json_conf.get('server_entity_root', None)
        _ler = gv.game_json_conf.get('lobby_entity_root', None)
        _ber = gv.game_json_conf.get('battle_entity_root', None)
        if _ser is None:
            # self.logger.error('conf file has no server_entity_root!')
            raise Exception('conf file has no server_entity_root!')
        if _ler is None:
            # self.logger.error('conf file has no server_entity_root!')
            raise Exception('conf file has no lobby_entity_root!')
        if _ber is None:
            # self.logger.error('conf file has no server_entity_root!')
            raise Exception('conf file has no battle_entity_root!')
            # return
        _temp = {_ser: ServerEntity,
                 _ler: LobbyEntity,
                 _ber: BattleEntity}
        for _ent_root, _ent_cls in _temp.items():
            entity_classes = EntityScanner.scan_entity_package(
                _ent_root, _ent_cls)
            entity_classes = entity_classes.items()
            for cls_name, cls in entity_classes:
                EntityFactory.instance().register_entity(cls_name, cls)

    @staticmethod
    def parse_json_conf(json_conf_path):
        # with open(r"../bin/win/conf/battle_server.json") as conf_file:
        with open(json_conf_path) as conf_file:
            # data = file.read()
            # _name = r'../bin/win/conf/battle_server.json'
            # file_name = r'D:\Documents\github\realtime-server\pycharm2020.1.3\bin\win\conf\battle_server.json'
            # file_name = r'C:\Users\b\Documents\github\realtime-server\pycharm2020.1.3\bin\win\conf\battle_server.json'
            # conf_file = open(file_name)
            json_conf = EnhancedJson.load(conf_file)
            # conf_file.close()
            gv.game_json_conf = json_conf

        # file_name = r'../bin/win/conf/battle_server.json'
        # # file_name = r'D:\Documents\github\realtime-server\pycharm2020.1.3\bin\win\conf\battle_server.json'
        # # file_name = r'C:\Users\b\Documents\github\realtime-server\pycharm2020.1.3\bin\win\conf\battle_server.json'
        # conf_file = open(file_name)
        # json_conf = json.load(conf_file)
        # conf_file.close()
        # gr.game_json_conf = json_conf
        return json_conf

    # def forward(self, addr, message):
    #     for _addr, _tcp_conn in self._addr_2_conn_map.items():
    #         # if w != writer:
    #             # w.write(f"{addr!r}: {message!r}\n".encode())
    #             # w.write(MsgpackSupport.encode(f"{addr!r}: {message!r}\n"))
    #         _tcp_conn.send_msg(f"{addr!r}: {message!r}\n")

    def add_conn(self, addr: typing.Tuple[str, int], conn):
        self._addr_2_conn_map[addr] = conn

    async def get_conn_by_addr(self, addr: typing.Tuple[str, int], rpc_handler: RpcHandler):
        _conn = self._addr_2_conn_map.get(addr, None)
        if _conn is None:
            reader, writer = await asyncio.open_connection(addr[0], addr[1])
            _conn = TcpConn(writer.get_extra_info('peername'), writer, reader, rpc_handler)
            self.add_conn(addr, _conn)
        return _conn

    async def handle_client_connected(self, reader, writer):
        # self.writers.append(writer)
        addr = writer.get_extra_info('peername')
        _tcp_conn = TcpConn(addr, writer, reader)
        # await _tcp_conn.loop()
        # _ppt = Puppet()

        # _tcp_conn.set_entity(_ppt)
        # _pbe = PuppetBindEntity()
        # _tcp_conn.set_entity(_pbe)
        # _tcp_conn.set_entity(_ppt)
        # _ppt.set_connection(_tcp_conn)
        # _pbe.set_connection(_tcp_conn)
        # _pbe.set_puppet(_ppt)
        # _ppt.set_puppet_bind_entity(_pbe)
        # _ppt.init_from_dict({})

        self.add_conn(addr, _tcp_conn)
        # self._addr_2_conn_map[addr] = _tcp_conn
        message = f"{addr!r} is connected !!!!"
        self._logger.debug(message)
        # _tcp_conn.loop()
        # self.forward(writer, addr, message)
        # while True:
        #     data = await reader.read(100)
        #     # message = data.decode().strip()
        #     message = MsgpackSupport.decode(data)
        #     self.forward(writer, addr, message)
        #     await writer.drain()
        #     if message == "exit":
        #         message = f"{addr!r} wants to close the connection."
        #         self.logger.debug(message)
        #         self.forward(writer, "Server", message)
        #         break
        # self.writers.remove(writer)
        # writer.close()

    async def start_server_task(self, _ip, _port):
        # server = await asyncio.start_server(
        #     handle_echo, '192.168.82.177', 8888)
        # _ip = gr.game_json_conf[gr.game_server_name]["ip"]
        # _port = gr.game_json_conf[gr.game_server_name]["port"]
        try:
            server = await asyncio.start_server(self.handle_client_connected, _ip, _port)
            # _start_srv_task = asyncio.create_task(asyncio.start_server(self.handle_client_connected, '192.168.82.177', 8888))
            # await _etcd_support_task
            # server = await _start_srv_task
            addr = server.sockets[0].getsockname()
            self._logger.debug(f'Server on {addr}')

            async with server:
                await server.serve_forever()
        except KeyboardInterrupt:
            self._logger.debug(f"\nShutting Down Server: {gv.game_server_name}...\n")
            # _loop = asyncio.get_running_loop()
            # _loop.stop()
            # _loop.close()
            # server.close()

            return
        except:
            # self.logger.debug("Unexpected error:", sys.exc_info()[0])
            self._logger.log_last_except()
            raise

    async def main(self):
        self.handle_sig()

        # etcd_addr_list = [('127.0.0.1', '2379'),]
        # etcd_addr_list = [('192.168.83.23', '2379'),]
        # etcd_addr_list = [
        #     (ip_port_map["ip"], str(ip_port_map["port"])) for ip_port_map in gr.game_json_conf["etcd_servers"]]

        _ip = gv.game_json_conf[gv.game_server_name]["ip"]
        _port = gv.game_json_conf[gv.game_server_name]["port"]
        # my_addr = (_ip, str(_port))
        #
        # service_module_dict = {"BattleAllocatorCenter": ""} if gr.game_server_name == "battle_0" else {
        #     "BattleAllocatorStub": ""}
        #
        # self._etcd_service_node = ServiceNode(etcd_addr_list, my_addr, service_module_dict)
        # # self._etcd_service_node = ServiceNode(etcd_addr_list, my_addr, {"BattleAllocatorStub": ""})
        # gr.etcd_service_node = self._etcd_service_node
        # self._timer_hub.call_later(4, self._check_game_start)

        _etcd_support_task = asyncio.create_task(self.start_etcd_task(_ip, _port))
        _start_srv_task = asyncio.create_task(self.start_server_task(_ip, _port))

        await _etcd_support_task
        await _start_srv_task

    async def start_etcd_task(self, _ip, _port):
        etcd_addr_list = [
            (ip_port_map["ip"], str(ip_port_map["port"])) for ip_port_map in gv.game_json_conf["etcd_servers"]]

        # _ip = gr.game_json_conf[gr.game_server_name]["ip"]
        # _port = gr.game_json_conf[gr.game_server_name]["port"]
        my_addr = (_ip, str(_port))

        # service_module_dict = {"BattleAllocatorCenter": ""} if gr.game_server_name == "battle_0" else {
        #     "BattleAllocatorStub": ""}

        self._etcd_service_node = ServiceNode(
            etcd_addr_list, my_addr, gv.game_json_conf[gv.game_server_name]["etcd_tag"])
        # self._etcd_service_node = ServiceNode(etcd_addr_list, my_addr, {"BattleAllocatorStub": ""})
        gv.etcd_service_node = self._etcd_service_node
        await self._etcd_service_node.start()

    def handle_sig(self):

        def ask_exit(sig_name, loop):
            self._logger.debug('got signal %s: exit' % sig_name)
            try:
                loop.stop()
            except RuntimeError:
                pass

        if platform.system() != 'Linux':
            return
        # _loop = asyncio.get_running_loop()
        for _sig_name in {'SIGINT', 'SIGTERM'}:
            self._ev_loop.add_signal_handler(
                getattr(signal, _sig_name), functools.partial(ask_exit, _sig_name, self._ev_loop))

    def run(self):
        self._ev_loop.run_until_complete(self.main())
        # asyncio.run(self.main())

    # def _check_game_start(self):
    #     # 随机种子
    #     # random.seed()
    #     # 得到本机ip
    #     try:
    #         gr.local_ip = socket.gethostbyname(socket.gethostname())
    #     except socket.gaierror:
    #         gr.local_ip = '127.0.0.1'
    #     # self._register_singleton()
    #
    # # def _register_singleton(self):
    #     # 创建各种server/cluster singleton
    #     SingletonEntityManager.instance().register_centers_and_stubs(
    #         gr.game_server_name,
    #         lambda flag: self._register_centers_and_stubs_cb(flag))
    #
    # def _register_centers_and_stubs_cb(self, flag):
    #     pass


if __name__ == '__main__':
    game_server_name = sys.argv[1]
    server_json_conf_path = r"../bin/win/conf/battle_server.json"
    tcp_server = TcpServer(game_server_name, server_json_conf_path)
    # TCP_SERVER = tcp_server
    tcp_server.run()

    # loop = asyncio.get_event_loop()
    # loop.run_until_complete(main())
