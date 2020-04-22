#!/usr/bin/env python
# -*- coding: utf8 -*-
#
# $Id$
#
# Copyright (c) 2012-2014 "dark[-at-]gotohack.org"
#
# This file is part of pymobiledevice2
#
# pymobiledevice2 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#
from __future__ import print_function

import os
import struct
import plistlib
import posixpath
import logging
import re
from construct.core import Struct
from construct.lib.containers import Container
from construct import Const,  Int64ul

from pymobiledevice2.lockdown import LockdownClient

from cmd import Cmd
from past.builtins import xrange
from six import PY3
from pymobiledevice2.util import hexdump, parsePlist
from pprint import pprint

from pymobiledevice2.lockdown import LockdownClient
from pymobiledevice2.util import hexdump, parsePlist

MODEMASK =  0o0000777

AFC_OP_STATUS          = 0x00000001
AFC_OP_DATA            = 0x00000002    #Data */
AFC_OP_READ_DIR        = 0x00000003    #ReadDir */
AFC_OP_READ_FILE       = 0x00000004    #ReadFile */
AFC_OP_WRITE_FILE      = 0x00000005    #WriteFile */
AFC_OP_WRITE_PART      = 0x00000006    #WritePart */
AFC_OP_TRUNCATE        = 0x00000007    #TruncateFile */
AFC_OP_REMOVE_PATH     = 0x00000008    #RemovePath */
AFC_OP_MAKE_DIR        = 0x00000009    #MakeDir */
AFC_OP_GET_FILE_INFO   = 0x0000000a    #GetFileInfo */
AFC_OP_GET_DEVINFO     = 0x0000000b    #GetDeviceInfo */
AFC_OP_WRITE_FILE_ATOM = 0x0000000c    #WriteFileAtomic (tmp file+rename) */
AFC_OP_FILE_OPEN       = 0x0000000d    #FileRefOpen */
AFC_OP_FILE_OPEN_RES   = 0x0000000e    #FileRefOpenResult */
AFC_OP_READ            = 0x0000000f    #FileRefRead */
AFC_OP_WRITE           = 0x00000010    #FileRefWrite */
AFC_OP_FILE_SEEK       = 0x00000011    #FileRefSeek */
AFC_OP_FILE_TELL       = 0x00000012    #FileRefTell */
AFC_OP_FILE_TELL_RES   = 0x00000013    #FileRefTellResult */
AFC_OP_FILE_CLOSE      = 0x00000014    #FileRefClose */
AFC_OP_FILE_SET_SIZE   = 0x00000015    #FileRefSetFileSize (ftruncate) */
AFC_OP_GET_CON_INFO    = 0x00000016    #GetConnectionInfo */
AFC_OP_SET_CON_OPTIONS = 0x00000017    #SetConnectionOptions */
AFC_OP_RENAME_PATH     = 0x00000018    #RenamePath */
AFC_OP_SET_FS_BS       = 0x00000019    #SetFSBlockSize (0x800000) */
AFC_OP_SET_SOCKET_BS   = 0x0000001A    #SetSocketBlockSize (0x800000) */
AFC_OP_FILE_LOCK       = 0x0000001B    #FileRefLock */
AFC_OP_MAKE_LINK       = 0x0000001C    #MakeLink */
AFC_OP_SET_FILE_TIME   = 0x0000001E    #set st_mtime */

AFC_E_SUCCESS                = 0
AFC_E_UNKNOWN_ERROR          = 1
AFC_E_OP_HEADER_INVALID      = 2
AFC_E_NO_RESOURCES           = 3
AFC_E_READ_ERROR             = 4
AFC_E_WRITE_ERROR            = 5
AFC_E_UNKNOWN_PACKET_TYPE    = 6
AFC_E_INVALID_ARG            = 7
AFC_E_OBJECT_NOT_FOUND       = 8
AFC_E_OBJECT_IS_DIR          = 9
AFC_E_PERM_DENIED            =10
AFC_E_SERVICE_NOT_CONNECTED  =11
AFC_E_OP_TIMEOUT             =12
AFC_E_TOO_MUCH_DATA          =13
AFC_E_END_OF_DATA            =14
AFC_E_OP_NOT_SUPPORTED       =15
AFC_E_OBJECT_EXISTS          =16
AFC_E_OBJECT_BUSY            =17
AFC_E_NO_SPACE_LEFT          =18
AFC_E_OP_WOULD_BLOCK         =19
AFC_E_IO_ERROR               =20
AFC_E_OP_INTERRUPTED         =21
AFC_E_OP_IN_PROGRESS         =22
AFC_E_INTERNAL_ERROR         =23

AFC_E_MUX_ERROR              =30
AFC_E_NO_MEM                 =31
AFC_E_NOT_ENOUGH_DATA        =32
AFC_E_DIR_NOT_EMPTY          =33

AFC_FOPEN_RDONLY   = 0x00000001 #/**< r   O_RDONLY */
AFC_FOPEN_RW       = 0x00000002 #/**< r+  O_RDWR   | O_CREAT */
AFC_FOPEN_WRONLY   = 0x00000003 #/**< w   O_WRONLY | O_CREAT  | O_TRUNC */
AFC_FOPEN_WR       = 0x00000004 #/**< w+  O_RDWR   | O_CREAT  | O_TRUNC */
AFC_FOPEN_APPEND   = 0x00000005 #/**< a   O_WRONLY | O_APPEND | O_CREAT */
AFC_FOPEN_RDAPPEND = 0x00000006 #/**< a+  O_RDWR   | O_APPEND | O_CREAT */

AFC_HARDLINK = 1
AFC_SYMLINK = 2

AFC_LOCK_SH = 1 | 4  #/**< shared lock */
AFC_LOCK_EX = 2 | 4  #/**< exclusive lock */
AFC_LOCK_UN = 8 | 4  #/**< unlock */

if PY3:
    AFCMAGIC = b"CFA6LPAA"
else:
    AFCMAGIC = "CFA6LPAA"

AFCPacket = Struct(
                   "magic" / Const(AFCMAGIC),
                   "entire_length" /Int64ul,
                   "this_length" / Int64ul,
                   "packet_num" / Int64ul,
                   "operation" / Int64ul,
                   )


class AFC2Client(object):
    def __init__(self, lockdown=None, serviceName="com.apple.afc2", service=None, udid=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.serviceName = serviceName
        self.lockdown = lockdown if lockdown else LockdownClient(udid=udid)
        self.service = service if service else self.lockdown.startService(self.serviceName)
        self.packet_num = 0


    def stop_session(self):
        self.logger.info("Disconecting...")
        self.service.close()


    def dispatch_packet(self, operation, data, this_length=0):
        afcpack = Container(magic=AFCMAGIC,
                   entire_length=40 + len(data),
                   this_length=40 + len(data),
                   packet_num=self.packet_num,
                   operation=operation)
        if this_length:
            afcpack.this_length = this_length
        header = AFCPacket.build(afcpack)
        self.packet_num += 1
        if PY3 and isinstance(data, str):
            data = data.encode('utf-8')
        self.service.send(header + data)


    def receive_data(self):
        res = self.service.recv_exact(40)
        status = AFC_E_SUCCESS
        data = ""
        if res:
            res = AFCPacket.parse(res)
            assert res["entire_length"] >= 40
            length = res["entire_length"] - 40
            data = self.service.recv_exact(length)
            if res.operation == AFC_OP_STATUS:
                if length != 8:
                    self.logger.error("Status length != 8")
                status = struct.unpack("<Q", data[:8])[0]
            elif res.operation != AFC_OP_DATA:
                pass#print "error ?", res
        return status, data


    def do_operation(self, opcode, data=""):
        try:
            self.dispatch_packet(opcode, data)
            data =  self.receive_data()
            return data
        except:
            self.lockdown = LockdownClient()
            self.service = self.lockdown.startService(self.serviceName)
            return self.do_operation(opcode, data)


    def list_to_dict(self, d):
        if PY3:
            if type(d) != str:
                d = d.decode('utf-8')
            else:
                x =0

        t = d.split("\x00")
        t = t[:-1]

        assert len(t) % 2 == 0
        res = {}
        for i in xrange(int(len(t)/2)):
            res[t[i*2]] = t[i*2 + 1]
        return res


    def get_device_infos(self):
        status, infos = self.do_operation(AFC_OP_GET_DEVINFO)
        if status == AFC_E_SUCCESS:
            return self.list_to_dict(infos)


    def read_directory(self, dirname):
        status, data = self.do_operation(AFC_OP_READ_DIR, dirname)
        if status == AFC_E_SUCCESS:
            if PY3:
                data = data.decode('utf-8')
            return [x for x in data.split("\x00") if x != ""]
        return []


    def make_directory(self, dirname):
        status, data = self.do_operation(AFC_OP_MAKE_DIR, dirname)
        return status


    def remove_directory(self, dirname):
        info = self.get_file_info(dirname)
        if not info or info.get("st_ifmt") != "S_IFDIR":
            self.logger.info("remove_directory: %s not S_IFDIR", dirname)
            return

        for d in self.read_directory(dirname):
            if d == "." or d == ".." or d == "":
                continue

            info = self.get_file_info(dirname + "/" + d)
            if info.get("st_ifmt") == "S_IFDIR":
                self.remove_directory(dirname + "/" + d)
            else:
                self.logger.info("%s/%s", dirname, d)
                self.file_remove(dirname + "/" + d)
        assert len(self.read_directory(dirname)) == 2 #.. et .
        return self.file_remove(dirname)


    def get_file_info(self, filename):
        status, data = self.do_operation(AFC_OP_GET_FILE_INFO, filename)
        if status == AFC_E_SUCCESS:
            return self.list_to_dict(data)


    def make_link(self, target, linkname, type=AFC_SYMLINK):
        if PY3:
            linkname = linkname.encode('utf-8')
            separator = b"\x00"
        else:
            separator = "\x00"
        status, data = self.do_operation(AFC_OP_MAKE_LINK, struct.pack("<Q", type) + target + separator + linkname + separator)
        self.logger.info("make_link: %s", status)
        return status


    def file_open(self, filename, mode=AFC_FOPEN_RDONLY):
        if PY3:
            filename = filename.encode('utf-8')
            separator = b"\x00"
        else:
            separator = "\x00"
        status, data = self.do_operation(AFC_OP_FILE_OPEN, struct.pack("<Q", mode) + filename + separator)
        return struct.unpack("<Q", data)[0] if data else None


    def file_close(self, handle):
        status, data = self.do_operation(AFC_OP_FILE_CLOSE, struct.pack("<Q", handle))
        return status


    def file_remove(self, filename):
        if PY3:
            filename = filename.encode('utf-8')
            separator = b"\x00"
        else:
            separator = "\x00"
        status, data = self.do_operation(AFC_OP_REMOVE_PATH, filename + separator)
        return status


    def file_rename(self, old, new):
        if PY3:
            old = old.encode('utf-8')
            new = new.encode('utf-8')
            separator = b"\x00"
        else:
            separator = "\x00"
        status, data = self.do_operation(AFC_OP_RENAME_PATH, old + separator + new + separator)
        return status



    def file_read(self, handle, sz):
        MAXIMUM_READ_SIZE = 1 << 16
        full_size = sz
        data = ""
        if PY3:
            data = b""
        while sz > 0:
            print(str(  (len(data) / full_size )   * 100  ) + "\r")
            if sz > MAXIMUM_READ_SIZE:
                toRead = MAXIMUM_READ_SIZE
            else:
                toRead = sz
            try:
                self.dispatch_packet(AFC_OP_READ, struct.pack("<QQ", handle, toRead))
                s, d = self.receive_data()
            except:
                import traceback
                traceback.print_exc()
                self.lockdown = LockdownClient()
                self.service = self.lockdown.startService("com.apple.afc")
                return  self.file_read(handle, sz)

            if s != AFC_E_SUCCESS:
                break
            sz -= toRead
            data += d
        return data


    def file_read_v2(self, handle, sz, local_file):
        MAXIMUM_READ_SIZE = 1 << 16
        full_size = sz
        data = ""
        if PY3:
            data = b""

        while sz > 0:
            with open(local_file, "ab") as local_file_handle:
                if sz > MAXIMUM_READ_SIZE:
                    toRead = MAXIMUM_READ_SIZE
                else:
                    toRead = sz
                try:
                    self.dispatch_packet(AFC_OP_READ, struct.pack("<QQ", handle, toRead))
                    s, d = self.receive_data()
                    if len(d) == 0:
                        print(local_file + " appears to be an empty file")
                        local_file_handle.write(b"")
                    else:
                        local_file_handle.write(d)
                except:
                    import traceback
                    traceback.print_exc()
                    self.lockdown = LockdownClient()
                    self.service = self.lockdown.startService("com.apple.afc")
                    return  self.file_read(handle, sz)

                if s != AFC_E_SUCCESS:
                    break
                sz -= toRead
                #data += d
        return


    def file_write(self, handle, data):
        MAXIMUM_WRITE_SIZE = 1 << 15
        hh = struct.pack("<Q", handle)
        segments = int(len(data) / MAXIMUM_WRITE_SIZE)
        try:
            for i in xrange(segments):
                self.dispatch_packet(AFC_OP_WRITE,
                                 hh + data[i*MAXIMUM_WRITE_SIZE:(i+1)*MAXIMUM_WRITE_SIZE],
                                     this_length=48)
                s, d = self.receive_data()
                if s != AFC_E_SUCCESS:
                    self.logger.error("file_write error: %d", s)
                    break
            if len(data) % MAXIMUM_WRITE_SIZE:
                self.dispatch_packet(AFC_OP_WRITE,
                                     hh + data[segments*MAXIMUM_WRITE_SIZE:],
                                     this_length=48)
                s, d = self.receive_data()
        except:
            self.lockdown = LockdownClient()
            self.service = self.lockdown.startService(self.serviceName)
            self.file_write(handle,data)
        return s


    def get_file_contents(self, filename):
        info = self.get_file_info(filename)
        if info:
            if info['st_ifmt'] == 'S_IFLNK':
                filename =  info['LinkTarget']

            if info['st_ifmt'] == 'S_IFDIR':
                self.logger.info("%s is directory...", filename)
                return

            self.logger.info("Reading: %s", filename)
            h = self.file_open(filename)
            if not h:
                return
            d = self.file_read(h, int(info["st_size"]))
            self.file_close(h)
            return d
        return

    def get_file_contents_v2(self, filename, local_file):
        info = self.get_file_info(filename)
        if info:
            if info['st_ifmt'] == 'S_IFLNK':
                filename =  info['LinkTarget']

            if info['st_ifmt'] == 'S_IFDIR':
                self.logger.info("%s is directory...", filename)
                return

            self.logger.info("Reading: %s", filename)
            h = self.file_open(filename)
            if not h:
                return
            self.file_read_v2(h, int(info["st_size"]), local_file)
            self.file_close(h)

        return


    def set_file_contents(self, filename, data):
        h = self.file_open(filename, AFC_FOPEN_WR)
        if not h:
            return
        d = self.file_write(h, data)
        self.file_close(h)


    def dir_walk(self, dirname):
        dirs = []
        files = []
        for fd in self.read_directory(dirname):
            if PY3 and isinstance(fd, bytes):
                fd = fd.decode('utf-8')
            if fd in ('.', '..', ''):
                continue
            infos = self.get_file_info(posixpath.join(dirname, fd))
            if infos and infos.get('st_ifmt') == 'S_IFDIR':
                dirs.append(fd)
            else:
                files.append(fd)

        yield dirname, dirs, files

        if dirs:
            for d in dirs:
                for walk_result in self.dir_walk(posixpath.join(dirname, d)):
                    yield walk_result

    def pull_file(self, remote_file, local_file):
        if not os.path.isfile(local_file):
            self.get_file_contents_v2(remote_file, local_file)



    def read_buffer(self, remote_file, size, local_file):
        x = 0

    def download_file(self, remote_file, local_file):

        max_blocks = 102400

        if not os.path.isfile(local_file):
            info = self.get_file_info(remote_file)
            if info['st_ifmt'] == 'S_IFLNK':
                remote_file =  info['LinkTarget']

            block_count = int(info['st_blocks'])
            if block_count > max_blocks:
                counter = max_blocks
                remaining_blocks = block_count
                while remaining_blocks > 0:
                    num_blocks_to_read = min(max_blocks, remaining_blocks)
                    handle = self.file_open(remote_file, num_blocks_to_read)
                    try:
                        self.dispatch_packet(AFC_OP_READ, struct.pack("<QQ", handle, 65536))
                        s, d = self.receive_data()
                    except:
                        import traceback
                        traceback.print_exc()
                        self.lockdown = LockdownClient()
                        self.service = self.lockdown.startService("com.apple.afc2")


    def handle_dir_pull(self, parent_dir, fd, output):
        if parent_dir == "/":
            new_folder = parent_dir + fd


        else:
            new_folder = parent_dir + '/' + fd

        new_folder = re.sub('[<>:"|?*]', '_', new_folder)
        local_folder = output + "\\" + new_folder.strip()
        if not os.path.exists(local_folder):
            self.logger.info("Creating Folder: " + new_folder)
            os.makedirs(local_folder)

        if new_folder is not '':
            self.pull_directory(new_folder, output)

    def handle_file_pull(self, parent_dir, fd, infos, output):
        if parent_dir == "/":
            new_file = parent_dir + fd


        else:
            new_file = parent_dir + '/' + fd

        new_file = re.sub('[<>:"|?*]', '_', new_file)
        local_file = output + "\\" + new_file.strip()
        parent_local_folder = (local_file[::-1].split("/"))
        local_single_file = parent_local_folder[0][::-1]
        del parent_local_folder[0]
        parent_local_folder = ("\\".join(parent_local_folder))[::-1]
        if parent_local_folder.endswith(' '):
            parent_local_folder = parent_local_folder[:-1]
            local_file = parent_local_folder + "\\" + local_single_file
        if not os.path.exists(parent_local_folder):
            os.makedirs(parent_local_folder)
        if infos is not None:
            if infos['st_size'] == '0':
                open(local_file, 'a').close()
        self.pull_file(new_file, local_file)

    def pull_directory(self, parent_dir, output):

        windows_reserved_names = ['CON', 'PRN', 'AUX', 'CLOCK$', 'NUL', 'COM1', 'LPT1', 'LPT2', 'LPT3',
                                  'COM2', 'COM3', 'COM4']

        for fd in self.read_directory(parent_dir):
            if PY3 and isinstance(fd, bytes):
                fd = fd.decode('utf-8')
            if fd in ('.', '..', ''):
                continue
            infos = self.get_file_info(posixpath.join(parent_dir, fd))

            if infos and infos.get('st_ifmt') == 'S_IFDIR':

                '''Handle folder creating / pulling'''
                if fd.upper() in windows_reserved_names:
                    fd = fd + "_MEAT_RENAMED"
                self.handle_dir_pull(parent_dir, fd, output)


            else:
                '''Handle file creating / pulling'''
                if fd.upper() in windows_reserved_names:
                    fd = fd + "_MEAT_RENAMED"
                self.handle_file_pull(parent_dir, fd, infos, output)



class AFCClient(object):
    def __init__(self, lockdown=None, serviceName="com.apple.afc", service=None, udid=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.serviceName = serviceName
        self.lockdown = lockdown if lockdown else LockdownClient(udid=udid)
        self.service = service if service else self.lockdown.startService(self.serviceName)
        self.packet_num = 0


    def stop_session(self):
        self.logger.info("Disconecting...")
        self.service.close()


    def dispatch_packet(self, operation, data, this_length=0):
        afcpack = Container(magic=AFCMAGIC,
                   entire_length=40 + len(data),
                   this_length=40 + len(data),
                   packet_num=self.packet_num,
                   operation=operation)
        if this_length:
            afcpack.this_length = this_length
        header = AFCPacket.build(afcpack)
        self.packet_num += 1
        if PY3 and isinstance(data, str):
            data = data.encode('utf-8')
        self.service.send(header + data)


    def receive_data(self):
        res = self.service.recv_exact(40)
        status = AFC_E_SUCCESS
        data = ""
        if res:
            res = AFCPacket.parse(res)
            assert res["entire_length"] >= 40
            length = res["entire_length"] - 40
            data = self.service.recv_exact(length)
            if res.operation == AFC_OP_STATUS:
                if length != 8:
                    self.logger.error("Status length != 8")
                status = struct.unpack("<Q", data[:8])[0]
            elif res.operation != AFC_OP_DATA:
                pass#print "error ?", res
        return status, data


    def do_operation(self, opcode, data=""):
        try:
            self.dispatch_packet(opcode, data)
            data =  self.receive_data()
            return data
        except:
            self.lockdown = LockdownClient()
            self.service = self.lockdown.startService(self.serviceName)
            return self.do_operation(opcode, data)


    def list_to_dict(self, d):
        if PY3:
            if type(d) != str:
                d = d.decode('utf-8')
            else:
                x =0

        t = d.split("\x00")
        t = t[:-1]

        assert len(t) % 2 == 0
        res = {}
        for i in xrange(int(len(t)/2)):
            res[t[i*2]] = t[i*2 + 1]
        return res


    def get_device_infos(self):
        status, infos = self.do_operation(AFC_OP_GET_DEVINFO)
        if status == AFC_E_SUCCESS:
            return self.list_to_dict(infos)


    def read_directory(self, dirname):
        status, data = self.do_operation(AFC_OP_READ_DIR, dirname)
        if status == AFC_E_SUCCESS:
            if PY3:
                data = data.decode('utf-8')
            return [x for x in data.split("\x00") if x != ""]
        return []


    def make_directory(self, dirname):
        status, data = self.do_operation(AFC_OP_MAKE_DIR, dirname)
        return status


    def remove_directory(self, dirname):
        info = self.get_file_info(dirname)
        if not info or info.get("st_ifmt") != "S_IFDIR":
            self.logger.info("remove_directory: %s not S_IFDIR", dirname)
            return

        for d in self.read_directory(dirname):
            if d == "." or d == ".." or d == "":
                continue

            info = self.get_file_info(dirname + "/" + d)
            if info.get("st_ifmt") == "S_IFDIR":
                self.remove_directory(dirname + "/" + d)
            else:
                self.logger.info("%s/%s", dirname, d)
                self.file_remove(dirname + "/" + d)
        assert len(self.read_directory(dirname)) == 2 #.. et .
        return self.file_remove(dirname)


    def get_file_info(self, filename):
        status, data = self.do_operation(AFC_OP_GET_FILE_INFO, filename)
        if status == AFC_E_SUCCESS:
            return self.list_to_dict(data)


    def make_link(self, target, linkname, type=AFC_SYMLINK):
        if PY3:
            linkname = linkname.encode('utf-8')
            separator = b"\x00"
        else:
            separator = "\x00"
        status, data = self.do_operation(AFC_OP_MAKE_LINK, struct.pack("<Q", type) + target + separator + linkname + separator)
        self.logger.info("make_link: %s", status)
        return status


    def file_open(self, filename, mode=AFC_FOPEN_RDONLY):
        if PY3:
            filename = filename.encode('utf-8')
            separator = b"\x00"
        else:
            separator = "\x00"
        status, data = self.do_operation(AFC_OP_FILE_OPEN, struct.pack("<Q", mode) + filename + separator)
        return struct.unpack("<Q", data)[0] if data else None


    def file_close(self, handle):
        status, data = self.do_operation(AFC_OP_FILE_CLOSE, struct.pack("<Q", handle))
        return status


    def file_remove(self, filename):
        if PY3:
            filename = filename.encode('utf-8')
            separator = b"\x00"
        else:
            separator = "\x00"
        status, data = self.do_operation(AFC_OP_REMOVE_PATH, filename + separator)
        return status


    def file_rename(self, old, new):
        if PY3:
            old = old.encode('utf-8')
            new = new.encode('utf-8')
            separator = b"\x00"
        else:
            separator = "\x00"
        status, data = self.do_operation(AFC_OP_RENAME_PATH, old + separator + new + separator)
        return status



    def file_read(self, handle, sz):
        MAXIMUM_READ_SIZE = 1 << 16
        full_size = sz
        data = ""
        if PY3:
            data = b""
        while sz > 0:
            print(str(  (len(data) / full_size )   * 100  ) + "\r")
            if sz > MAXIMUM_READ_SIZE:
                toRead = MAXIMUM_READ_SIZE
            else:
                toRead = sz
            try:
                self.dispatch_packet(AFC_OP_READ, struct.pack("<QQ", handle, toRead))
                s, d = self.receive_data()
            except:
                import traceback
                traceback.print_exc()
                self.lockdown = LockdownClient()
                self.service = self.lockdown.startService("com.apple.afc")
                return  self.file_read(handle, sz)

            if s != AFC_E_SUCCESS:
                break
            sz -= toRead
            data += d
        return data


    def file_read_v2(self, handle, sz, local_file):
        MAXIMUM_READ_SIZE = 1 << 16
        full_size = sz
        data = ""
        if PY3:
            data = b""

        while sz > 0:
            with open(local_file, "ab") as local_file_handle:
                if sz > MAXIMUM_READ_SIZE:
                    toRead = MAXIMUM_READ_SIZE
                else:
                    toRead = sz
                try:
                    self.dispatch_packet(AFC_OP_READ, struct.pack("<QQ", handle, toRead))
                    s, d = self.receive_data()
                    local_file_handle.write(d)
                except:
                    import traceback
                    traceback.print_exc()
                    self.lockdown = LockdownClient()
                    self.service = self.lockdown.startService("com.apple.afc")
                    return  self.file_read(handle, sz)

                if s != AFC_E_SUCCESS:
                    break
                sz -= toRead
                #data += d
        return


    def file_write(self, handle, data):
        MAXIMUM_WRITE_SIZE = 1 << 15
        hh = struct.pack("<Q", handle)
        segments = int(len(data) / MAXIMUM_WRITE_SIZE)
        try:
            for i in xrange(segments):
                self.dispatch_packet(AFC_OP_WRITE,
                                 hh + data[i*MAXIMUM_WRITE_SIZE:(i+1)*MAXIMUM_WRITE_SIZE],
                                     this_length=48)
                s, d = self.receive_data()
                if s != AFC_E_SUCCESS:
                    self.logger.error("file_write error: %d", s)
                    break
            if len(data) % MAXIMUM_WRITE_SIZE:
                self.dispatch_packet(AFC_OP_WRITE,
                                     hh + data[segments*MAXIMUM_WRITE_SIZE:],
                                     this_length=48)
                s, d = self.receive_data()
        except:
            self.lockdown = LockdownClient()
            self.service = self.lockdown.startService(self.serviceName)
            self.file_write(handle,data)
        return s


    def get_file_contents(self, filename):
        info = self.get_file_info(filename)
        if info:
            if info['st_ifmt'] == 'S_IFLNK':
                filename =  info['LinkTarget']

            if info['st_ifmt'] == 'S_IFDIR':
                self.logger.info("%s is directory...", filename)
                return

            self.logger.info("Reading: %s", filename)
            h = self.file_open(filename)
            if not h:
                return
            d = self.file_read(h, int(info["st_size"]))
            self.file_close(h)
            return d
        return

    def get_file_contents_v2(self, filename, local_file):
        info = self.get_file_info(filename)
        if info:
            if info['st_ifmt'] == 'S_IFLNK':
                filename =  info['LinkTarget']

            if info['st_ifmt'] == 'S_IFDIR':
                self.logger.info("%s is directory...", filename)
                return

            self.logger.info("Reading: %s", filename)
            h = self.file_open(filename)
            if not h:
                return
            self.file_read_v2(h, int(info["st_size"]), local_file)
            self.file_close(h)

        return


    def set_file_contents(self, filename, data):
        h = self.file_open(filename, AFC_FOPEN_WR)
        if not h:
            return
        d = self.file_write(h, data)
        self.file_close(h)


    def dir_walk(self, dirname):
        dirs = []
        files = []
        for fd in self.read_directory(dirname):
            if PY3 and isinstance(fd, bytes):
                fd = fd.decode('utf-8')
            if fd in ('.', '..', ''):
                continue
            infos = self.get_file_info(posixpath.join(dirname, fd))
            if infos and infos.get('st_ifmt') == 'S_IFDIR':
                dirs.append(fd)
            else:
                files.append(fd)

        yield dirname, dirs, files

        if dirs:
            for d in dirs:
                for walk_result in self.dir_walk(posixpath.join(dirname, d)):
                    yield walk_result

    def pull_file(self, remote_file, local_file):
        if not os.path.isfile(local_file):
            self.get_file_contents_v2(remote_file, local_file)



    def read_buffer(self, remote_file, size, local_file):
        x = 0

    def download_file(self, remote_file, local_file):

        max_blocks = 102400

        if not os.path.isfile(local_file):
            info = self.get_file_info(remote_file)
            if info['st_ifmt'] == 'S_IFLNK':
                remote_file =  info['LinkTarget']

            block_count = int(info['st_blocks'])
            if block_count > max_blocks:
                counter = max_blocks
                remaining_blocks = block_count
                while remaining_blocks > 0:
                    num_blocks_to_read = min(max_blocks, remaining_blocks)
                    handle = self.file_open(remote_file, num_blocks_to_read)
                    try:
                        self.dispatch_packet(AFC_OP_READ, struct.pack("<QQ", handle, 65536))
                        s, d = self.receive_data()
                    except:
                        import traceback
                        traceback.print_exc()
                        self.lockdown = LockdownClient()
                        self.service = self.lockdown.startService("com.apple.afc2")


    def pull_directory(self, parent_dir, output):

        windows_reserved_names = ['CON', 'PRN', 'AUX', 'CLOCK$', 'NUL', 'COM1', 'LPT1', 'LPT2', 'LPT3',
                                  'COM2', 'COM3', 'COM4']

        for fd in self.read_directory(parent_dir):
            if PY3 and isinstance(fd, bytes):
                fd = fd.decode('utf-8')
            if fd in ('.', '..', ''):
                continue
            infos = self.get_file_info(posixpath.join(parent_dir, fd))
            if infos and infos.get('st_ifmt') == 'S_IFDIR':

                if parent_dir == "/":
                    if fd in windows_reserved_names:
                        fd = fd + "_MEAT_RENAMED"
                    new_folder = parent_dir + fd


                else:
                    if fd in windows_reserved_names:
                        fd = fd + "_MEAT_RENAMED"
                    new_folder = parent_dir + '/' + fd

                new_folder = re.sub('[<>:"|?*]', '_', new_folder)
                local_folder = output + "\\" + new_folder.strip()
                if not os.path.exists(local_folder):
                    self.logger.info("Creating Folder: " + new_folder)
                    os.makedirs(local_folder)


                if new_folder is not '':
                    self.pull_directory(new_folder, output)


            else:
                if parent_dir == "/":
                    new_file = parent_dir + fd


                else:
                    new_file = parent_dir + '/' + fd

                new_file = re.sub('[<>:"|?*]', '_', new_file)
                local_file = output + "\\" + new_file.strip()
                #self.download_file(new_file, local_file)
                parent_local_folder = (local_file[::-1].split("/"))
                local_single_file = parent_local_folder[0][::-1]
                del parent_local_folder[0]
                parent_local_folder = ("\\".join(parent_local_folder))[::-1]
                if parent_local_folder.endswith(' '):
                    parent_local_folder = parent_local_folder[:-1]
                    local_file = parent_local_folder + "\\" + local_single_file
                if not os.path.exists(parent_local_folder):
                    os.makedirs(parent_local_folder)
                if infos is not None:
                    if infos['st_size'] == '0':
                        open(local_file, 'a').close()
                self.pull_file(new_file, local_file)


class AFCShell(Cmd):

    def __init__(self, afcname='com.apple.afc', completekey='tab', stdin=None, stdout=None, client=None, udid=None, logger=None):
        Cmd.__init__(self, completekey=completekey, stdin=stdin, stdout=stdout)
        self.logger = logger or logging.getLogger(__name__)
        self.lockdown = LockdownClient()
        self.afc = client if client else AFCClient(self.lockdown, serviceName=afcname, udid=udid)
        self.curdir = '/'
        self.prompt = 'AFC$ ' + self.curdir + ' '
        self.complete_cat = self._complete
        self.complete_ls = self._complete


    def do_exit(self, p):
        return True


    def do_quit(self, p):
        return True


    def do_pwd(self, p):
        print(self.curdir)


    def do_link(self, p):
        z = p.split()
        self.afc.make_link(AFC_SYMLINK, z[0], z[1])


    def do_cd(self, p):
        if not p.startswith("/"):
            new = self.curdir + "/" + p
        else:
            new = p

        new = os.path.normpath(new).replace("\\","/").replace("//","/")
        if self.afc.read_directory(new):
            self.curdir = new
            self.prompt = "AFC$ %s " % new
        else:
            self.logger.error("%s does not exist", new)

    def _complete(self, text, line, begidx, endidx):
        filename = text.split("/")[-1]
        dirname = "/".join(text.split("/")[:-1])
        return [dirname + "/" + x for x in self.afc.read_directory(self.curdir + "/" + dirname) if x.startswith(filename)]


    def do_ls(self, p):
        data = []
        d = self.afc.read_directory(self.curdir + "/" + p)
        if d:
            for dd in d:
                if dd != ".":
                    if dd != "..":
                        data.append(dd)
        return data


    def do_cat(self, p):
        data = self.afc.get_file_contents(self.curdir + "/" + p)
        if data and p.endswith(".plist"):
            pprint(parsePlist(data))
        else:
            print(data)


    def do_rm(self, p):
        f =  self.afc.get_file_info(self.curdir + "/" + p)
        if f['st_ifmt'] == 'S_IFDIR':
            d = self.afc.remove_directory(self.curdir + "/" + p)
        else:
            d = self.afc.file_remove(self.curdir + "/" + p)


    def do_pull(self, user_args):
        args = user_args.split()
        if len(args) != 2:
            out = "."
            path = user_args
        else:
            out = args[1]
            path = args[0]

        f =  self.afc.get_file_info(self.curdir + "/" + path)
        if not f:
            print("Source file does not exist..")
            return

        out_path = out + "/" + path
        if f['st_ifmt'] == 'S_IFDIR':

            if not os.path.isdir(out_path):
                os.makedirs(out_path, MODEMASK)

            for d in self.afc.read_directory(path):
                if d == "." or d == ".." or d == "":
                    continue
                self.do_pull(path + "/" + d + " " + out)
        else:
            data = self.afc.get_file_contents(self.curdir + "/" + path)
            if data:
                if data and path.endswith(".plist"):
                    z = parsePlist(data)
                    plistlib.writePlist(z, out_path)
                else:
                    with open(out_path, 'wb+') as f:
                        f.write(data)

    def do_push(self, p):
        fromTo = p.split()
        if len(fromTo) != 2:
            return
        print("from %s to %s" % (fromTo[0], fromTo[1]))
        if os.path.isdir(fromTo[0]):
            self.afc.make_directory(os.path.join(fromTo[1]))
            for x in os.listdir(fromTo[0]):
                if x.startswith("."):
                    continue
                path = os.path.join(fromTo[0],x)
                self.do_push(path + " " + fromTo[1]+ "/" + path)
        else:
            if not fromTo[0].startswith("."):
                data = open(fromTo[0], "rb").read()
                self.afc.set_file_contents(self.curdir + "/" + fromTo[1], data)


    def do_head(self, p):
        print(self.afc.get_file_contents(self.curdir + "/" + p)[:32])


    def do_hexdump(self, p):
        t = p.split(" ")
        l = 0
        if len(t) < 1:
            return
        if len(t) == 2:
            l = int(t[1])
        z = self.afc.get_file_contents(self.curdir + "/" + t[0])
        if not z:
            return
        if l:
            z = z[:l]
        hexdump(z)


    def do_mkdir(self, p):
        print(self.afc.make_directory(p))


    def do_rmdir(self, p):
        return self.afc.remove_directory(p)


    def do_infos(self, p):
        for k,v in self.afc.get_device_infos().items():
            print(k, '\t:\t',v)


    def do_mv(self, p):
        t = p.split()
        return self.afc.rename_path(t[0], t[1])

class AFC2Shell(Cmd):

    def __init__(self, afcname='com.apple.afc2', completekey='tab', stdin=None, stdout=None, client=None, udid=None, logger=None):
        Cmd.__init__(self, completekey=completekey, stdin=stdin, stdout=stdout)
        self.logger = logger or logging.getLogger(__name__)
        self.lockdown = LockdownClient()
        self.afc = client if client else AFC2Client(self.lockdown, udid=udid)
        self.curdir = '/'
        self.prompt = 'AFC$ ' + self.curdir + ' '
        self.complete_cat = self._complete
        self.complete_ls = self._complete


    def do_exit(self, p):
        return True


    def do_quit(self, p):
        return True


    def do_pwd(self, p):
        print(self.curdir)


    def do_link(self, p):
        z = p.split()
        self.afc.make_link(AFC_SYMLINK, z[0], z[1])


    def do_cd(self, p):
        if not p.startswith("/"):
            new = self.curdir + "/" + p
        else:
            new = p

        new = os.path.normpath(new).replace("\\","/").replace("//","/")
        if self.afc.read_directory(new):
            self.curdir = new
            self.prompt = "AFC$ %s " % new
        else:
            self.logger.error("%s does not exist", new)

    def _complete(self, text, line, begidx, endidx):
        filename = text.split("/")[-1]
        dirname = "/".join(text.split("/")[:-1])
        return [dirname + "/" + x for x in self.afc.read_directory(self.curdir + "/" + dirname) if x.startswith(filename)]


    def do_ls(self, p):
        data = []
        d = self.afc.read_directory(self.curdir + "/" + p)
        if d:
            for dd in d:
                if dd != ".":
                    if dd != "..":
                        data.append(dd)
        return data


    def do_cat(self, p):
        data = self.afc.get_file_contents(self.curdir + "/" + p)
        if data and p.endswith(".plist"):
            pprint(parsePlist(data))
        else:
            print(data)


    def do_rm(self, p):
        f =  self.afc.get_file_info(self.curdir + "/" + p)
        if f['st_ifmt'] == 'S_IFDIR':
            d = self.afc.remove_directory(self.curdir + "/" + p)
        else:
            d = self.afc.file_remove(self.curdir + "/" + p)







    def do_pull(self, user_args):
        args = user_args.split()
        if len(args) != 2:
            out = "."
            path = user_args
        else:
            out = args[1]
            path = args[0]

        f =  self.afc.get_file_info(self.curdir + "/" + path)
        if not f:
            print("Source file does not exist..")
            return

        out_path = out + "/" + path
        if f['st_ifmt'] == 'S_IFDIR':

            if not os.path.isdir(out_path):
                os.makedirs(out_path, MODEMASK)

            for d in self.afc.read_directory(path):
                if d == "." or d == ".." or d == "":
                    continue
                self.do_pull(path + "/" + d + " " + out)
        else:
            data = self.afc.get_file_contents(self.curdir + "/" + path)
            if data:
                if data and path.endswith(".plist"):
                    z = parsePlist(data)
                    plistlib.writePlist(z, out_path)
                else:
                    with open(out_path, 'wb+') as f:
                        f.write(data)

    def do_push(self, p):
        fromTo = p.split()
        if len(fromTo) != 2:
            return
        print("from %s to %s" % (fromTo[0], fromTo[1]))
        if os.path.isdir(fromTo[0]):
            self.afc.make_directory(os.path.join(fromTo[1]))
            for x in os.listdir(fromTo[0]):
                if x.startswith("."):
                    continue
                path = os.path.join(fromTo[0],x)
                self.do_push(path + " " + fromTo[1]+ "/" + path)
        else:
            if not fromTo[0].startswith("."):
                data = open(fromTo[0], "rb").read()
                self.afc.set_file_contents(self.curdir + "/" + fromTo[1], data)


    def do_head(self, p):
        print(self.afc.get_file_contents(self.curdir + "/" + p)[:32])


    def do_hexdump(self, p):
        t = p.split(" ")
        l = 0
        if len(t) < 1:
            return
        if len(t) == 2:
            l = int(t[1])
        z = self.afc.get_file_contents(self.curdir + "/" + t[0])
        if not z:
            return
        if l:
            z = z[:l]
        hexdump(z)


    def do_mkdir(self, p):
        print(self.afc.make_directory(p))


    def do_rmdir(self, p):
        return self.afc.remove_directory(p)


    def do_infos(self, p):
        for k,v in self.afc.get_device_infos().items():
            print(k, '\t:\t',v)


    def do_mv(self, p):
        t = p.split()
        return self.afc.rename_path(t[0], t[1])

    def pull_directory(self, parent_dir, output):

        for fd in self.read_directory(parent_dir):
            if PY3 and isinstance(fd, bytes):
                fd = fd.decode('utf-8')
            if fd in ('.', '..', ''):
                continue
            infos = self.get_file_info(posixpath.join(parent_dir, fd))
            if infos and infos.get('st_ifmt') == 'S_IFDIR':

                if parent_dir == "/":
                    new_folder = parent_dir + fd


                else:
                    new_folder = parent_dir + '/' + fd

                new_folder = re.sub('[<>:"|?*]', '_', new_folder)
                local_folder = output + "\\" + new_folder.strip()
                if not os.path.exists(local_folder):
                    self.logger.info("Creating Folder: " + new_folder)
                    os.makedirs(local_folder)


                if new_folder is not '':
                    self.pull_directory(new_folder, output)


            else:
                if parent_dir == "/":
                    new_file = parent_dir + fd


                else:
                    new_file = parent_dir + '/' + fd

                new_file = re.sub('[<>:"|?*]', '_', new_file)
                local_file = output + "\\" + new_file.strip()
                #self.download_file(new_file, local_file)
                parent_local_folder = (local_file[::-1].split("/"))
                local_single_file = parent_local_folder[0][::-1]
                del parent_local_folder[0]
                parent_local_folder = ("\\".join(parent_local_folder))[::-1]
                if parent_local_folder.endswith(' '):
                    parent_local_folder = parent_local_folder[:-1]
                    local_file = parent_local_folder + "\\" + local_single_file
                if not os.path.exists(parent_local_folder):
                    os.makedirs(parent_local_folder)
                if infos is not None:
                    if infos['st_size'] == '0':
                        open(local_file, 'a').close()
                self.pull_file(new_file, local_file)


#class AFC2Client(AFC2Client):
#    def __init__(self, lockdown=None,udid=None, logger=None):
#        super(AFC2Client, self).__init__(lockdown, serviceName="com.apple.afc2",udid=udid)



class AFCCrashLog(AFCClient):
    def __init__(self, lockdown=None, udid=None, logger=None):
        super(AFCCrashLog, self).__init__(lockdown, serviceName="com.apple.crashreportcopymobile", udid=udid)



if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    AFCShell().cmdloop("Hello iPhone!")
