#!/usr/bin/python

import socket
import dbus
import dbus.service
import dbus.mainloop.glib

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

ADAPTER = 'hci0'
A2DP_SINK_UUID = "0000110B-0000-1000-8000-00805F9B34FB"
SBC_CODEC = dbus.Byte(0x00)
SBC_CAPABILITIES = dbus.Array([dbus.Byte(0xff), dbus.Byte(0xff), dbus.Byte(2), dbus.Byte(64)])
SBC_CONFIGURATION = dbus.Array([dbus.Byte(0x21), dbus.Byte(0x15), dbus.Byte(2), dbus.Byte(32)])

MP3_CODEC = dbus.Byte(0x01)
MP3_CAPABILITIES = dbus.Array([dbus.Byte(0x3f), dbus.Byte(0x07), dbus.Byte(0xff), dbus.Byte(0xfe)])
MP3_CONFIGURATION = dbus.Array([dbus.Byte(0x21), dbus.Byte(0x02), dbus.Byte(0x00), dbus.Byte(0x80)])


class Bluez():
    
    def __init__(self):

        self.bus = dbus.SystemBus()
        self.adapters = {}


        self.bus.add_signal_receiver(self._interfaceAdded, dbus_interface='org.freedesktop.DBus.ObjectManager', signal_name = "InterfacesAdded")
        self.bus.add_signal_receiver(self._interfaceRemoved, dbus_interface='org.freedesktop.DBus.ObjectManager', signal_name = "InterfacesRemoved")
        self.bus.add_signal_receiver(self._propertiesChanged, dbus_interface='org.freedesktop.DBus.Properties', signal_name = "PropertiesChanged", path_keyword = "path")

        # Find the adapters and create the objects
        obj_mgr = dbus.Interface(self.bus.get_object("org.bluez", "/"), 'org.freedesktop.DBus.ObjectManager')
        objs = obj_mgr.GetManagedObjects()
        for obj_path in objs:
            obj = objs[obj_path]
            if 'org.bluez.Adapter1' in obj:
                adapt_name = obj_path.split('/')[3]
                self.adapters[adapt_name] = Adapter(self.bus, obj_path)
               
    def _interfaceAdded(self, path, interface):
        print("_interfaceAdded " + path + " | " + str(interface))
        adapt_name = path.split('/')[3]
        if 'org.bluez.Adapter1' in interface:
            self.adapters[adapt_name] = Adapter(self.bus, path)
        elif adapt_name in self.adapters:
            self.adapters[adapt_name]._interfaceAdded(path, interface)
                
    def _interfaceRemoved(self, path, interface):
        print("_interfaceRemoved " + path + " | " + str(interface))
        adapt_name = path.split('/')[3]
        if 'org.bluez.Adapter1' in interface:
            del self.adapters[path]
        elif adapt_name in self.adapters:
            self.adapters[adapt_name]._interfaceRemoved(path, interface)

    def _propertiesChanged(self, interface, changed, invalidated, path):
        if not path.startswith("/org/bluez/"):
            return

        print("_propertiesChanged " + path + " | " + str(interface) + " | " + str(changed) + " | " + str(invalidated))

        adapt_name = path.split('/')[3]
        if adapt_name in self.adapters:
            self.adapters[adapt_name]._propertiesChanged(interface, changed, invalidated, path)

    def getAdapter(self, adapt_name):
        if adapt_name in self.adapters:
            return self.adapters[adapt_name]
        return None


class Adapter():

    def __init__(self, bus, path):

        print("New adapter " + path)
        self.bus = bus
        self.path = path
        self.prop = dbus.Interface(self.bus.get_object("org.bluez", path), "org.freedesktop.DBus.Properties")
        self.devices = {}

        obj_mgr = dbus.Interface(self.bus.get_object("org.bluez", "/"), 'org.freedesktop.DBus.ObjectManager')
        objs = obj_mgr.GetManagedObjects()
        for obj_path in objs:
            obj = objs[obj_path]
            if 'org.bluez.Device1' in obj:
                dev_name = obj_path.split('/')[4]
                self.devices[dev_name] = Device(self.bus, obj_path)

    def __del__(self):
        print("Removed adapter " + self.path)

    def _interfaceAdded(self, path, interface):
        print("adapter _interfaceAdded " + path)
        spath = path.split('/')[4]
        dev_name = spath
        if 'org.bluez.Device1' in interface:
            self.devices[dev_name] = Device(self.bus, path)
        elif dev_name in self.devices and len(spath) > 5:
            self.devices[dev_name]._interfaceAdded(path, interface)
        
    def _interfaceRemoved(self, path, interface):
        print("adapter _interfaceRemoved " + path)
        dev_name = path.split('/')[4]
        if 'org.bluez.Device1' in interface:
            del self.devices[dev_name]
        elif dev_name in self.devices:
            self.devices[dev_name]._interfaceRemoved(path, interface)

    def _propertiesChanged(self, interface, changed, invalidated, path):
        print("adapter _propertiesChanged " + path)
        spath = path.split('/')

        if len(spath) >= 5:
            dev_name  = spath[4]
            if dev_name in self.devices:
                self.devices[dev_name]._propertiesChanged(interface, changed, invalidated, path)
            return

        # Handle out property change here
        
    def powerSet(self, status):
        print("Turning on adapter " + self.path)
        self.prop.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(status))

    def discoverableSet(self, status):
        print("Making adapter " + self.path + " discoverable")
        self.prop.Set("org.bluez.Adapter1", "Discoverable", dbus.Boolean(status))

    def mediaEndpointRegister(self):
        media = dbus.Interface(self.bus.get_object("org.bluez", self.path), "org.bluez.Media1")
        media_path = '/test/endpoint_' + self.path.split('/')[3]
        self.mediaEndpoint = MediaEndpoint(self.bus, media_path)
        properties = dbus.Dictionary({ "UUID" : A2DP_SINK_UUID, "Codec" : SBC_CODEC, "DelayReporting" : True, "Capabilities" : SBC_CAPABILITIES })
        media.RegisterEndpoint(media_path, properties)
        print("MediaEndpoint registered for " + self.path)



class Device():

    def __init__(self, bus, path):
        print("New device " + path)
        self.bus = bus
        self.path = path
        self.mediaTransports = {}

    def __del__(self):
        print("Removed device " + self.path)

    def _interfaceAdded(self, path, interface):
        print("device _interfaceAdded " + path)
        obj_name = path.split('/')[5]
        if 'org.bluez.MediaTransport1' in interface:
            self.mediaTransports[obj_name] = MediaTransport(self.bus, path)

    def _interfaceRemoved(self, path, interface):
        print("device _interfaceRemoved " + path)
        obj_name = path.split('/')[5]
        if 'org.bluez.MediaTransport1' in interface and obj_name in self.mediaTransports:
            del self.mediaTransports[obj_name]

    def _propertiesChanged(self, interface, changed, invalidated, path):
        print("device _propertiesChanged " + path)
        spath = path.split('/')

        if len(spath) >= 6:
            obj_name = spath[5]
            if 'org.bluez.MediaTransport1' in interface and obj_name in self.mediaTransports:
                self.mediaTransports[obj_name]._propertiesChanged(interface, changed, invalidated, path)

class MediaEndpoint(dbus.service.Object):

    def __init__(self, bus, path):
        self.bus = bus
        self.path = path
        super(MediaEndpoint, self).__init__(bus, path)

    @dbus.service.method("org.bluez.MediaEndpoint1", in_signature="ay", out_signature="ay")
    def SelectConfiguration(self, caps):
        print("SelectConfiguration (%s)" % (caps))
        return self.configuration


    @dbus.service.method("org.bluez.MediaEndpoint1", in_signature="oay", out_signature="")
    def SetConfiguration(self, transport, config):
        print("SetConfiguration (%s, %s)" % (transport, config))
        return

    @dbus.service.method("org.bluez.MediaEndpoint1", in_signature="o", out_signature="")
    def ClearConfiguration(self, transport):
        print("ClearConfiguration (%s)" % (transport))


    @dbus.service.method("org.bluez.MediaEndpoint1", in_signature="", out_signature="")
    def Release(self):
        print("Release")


class MediaTransport():

    def __init__(self, bus, path):
        print("New media transport " + path)
        self.bus = bus
        self.path = path
        self.pipeline = None

    def __del__(self):
        print("Removed media transport " + self.path)

    def _propertiesChanged(self, interface, changed, invalidated, path):
        print("mediaTransport _propertiesChanged " + path)

        if 'State' in changed and changed['State'] == 'pending':
            if self.pipeline:
                return

            self.pipeline = Gst.Pipeline.new("player")

            gst_bus = self.pipeline.get_bus()
            gst_bus.add_signal_watch()
            gst_bus.connect("message", self._gst_on_message)

            source = Gst.ElementFactory.make("avdtpsrc", "bluetooth-source")
            depay = Gst.ElementFactory.make("rtpsbcdepay", "depayloader")
            parse = Gst.ElementFactory.make("sbcparse", "parser")
            decoder = Gst.ElementFactory.make("sbcdec", "decoder")
            sink = Gst.ElementFactory.make("alsasink", "alsa-output")

            self.pipeline.add(source)
            self.pipeline.add(depay)
            self.pipeline.add(parse)
            self.pipeline.add(decoder)
            self.pipeline.add(sink)

            print(source.link(depay))
            print(depay.link(parse))
            print(parse.link(decoder))
            print(decoder.link(sink))

            source.set_property("transport", path)

            self.pipeline.set_state(Gst.State.PLAYING)

    def _gst_on_message(self, gst_bus, message):
        t = message.type
        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print("Error : %s " % err, debug)
        else:
            print(message.type, message.src)


def find_adapters():

    adapts = {}
    objs = obj_mgr.GetManagedObjects()
    for obj_path in objs:
    
        obj = objs[obj_path]
        if 'org.bluez.Adapter1' in obj:
            adapts[obj_path] = obj['org.bluez.Adapter1']

    return adapts

def main():

    bluez = Bluez()

    adapt = bluez.getAdapter(ADAPTER)

    if not adapt:
        return

    adapt.powerSet(True)
    adapt.discoverableSet(True)
    adapt.mediaEndpointRegister()


    Gst.init(None)
    GObject.threads_init()
    mainloop = GObject.MainLoop()
    mainloop.run()
    return


if __name__ == '__main__':
    main()
