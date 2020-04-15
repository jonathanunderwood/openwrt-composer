# openwrt-composer

An OpenWRT firmware builder which takes input from a YAML manifest.

OpenWRT composer takes a YAML manifest which specifies firmware images to build,
including what packages to add/remove from the firmware, and how to configure
the firmware. The idea is that the firmware image is regarded as immutable; any
change in configuration is achieved by producing a new firmware image and
loading that onto the device.

Configuration is specified in the YAML manifest, and leverages the NetJSONConfig
package to create valid configuration files which are then baked into the
firmware image.

Building of the image itself is done inside a container. Currently the Podman
container runtime is used, but adding Docker support is on the TODO list, and
wouldn't require much work at all.

*This project is still under heavy development. It will probably build you a
firmware that will turn your router into a brick.*


## The concept

The aim is to provide a reliable and simple way to produce custom OpenWRT
firmware images which allow device configuration and customization to be "baked
in" to the firmware. 

As such, the philosophy is to regard the firmware image as immutable; any change
in configuration is achieved by producing a new firmware image and loading that
onto the device.

The concept is simple:
- Leverage the [OpenWRT image
builder](https://openwrt.org/docs/guide-user/additional-software/imagebuilder)
to build custom firmwares.
- Use a YAML manifest to determine what packages are installed in the firmware
- Use the same YAML manifest to create a configuration for the firmware

As such, a single YAML manifest specifies the contents and configuration of a
firmware. That makes it very easy to share and collaborate firmware
configurations.


## Usage

The command line tool is `owc`:
```
$ owc
Usage: owc [OPTIONS] CONFIG_FILE MANIFEST_FILE
Try "owc --help" for help.
```

The command expects two arguments, both of which should be
[YAML](https://yaml.org) files. The `CONFIG_FILE` argument corresponds to a file
that configures the tool itself. the `MANIFEST_FILE` specifies the firmwares to
be built.

An example `CONFIG_FILE`:

```yaml
work_dir: ./build
openwrt_base_url: https://downloads.openwrt.org/
```

An example `MANIFEST_FILE`:

```yaml
firmwares:
  - target: lantiq
    sub_target: xrx200
    profile:  bt_homehub-v5a
    version: 18.06.1
    name: router
    packages:
      add:
        - dnsmasq-full
      remove:
        - dnsmasq
```

### Firmware Configuration

There are currently two overlapping ways of specifying the configuration of the
firmware in the manifest. In both cases, the end result is the same: the
firmware contains customized files which configure the device.

#### Option 1: using the `files` section in the manifest

The `files` section of a firmware image specification can specify the contents
of files to include in the firmware. An example is shown below:

```yaml
firmwares:
  - target: lantiq
    sub_target: xrx200
    profile:  bt_homehub-v5a
    version: 18.06.1
    name: router
    packages:
      add:
        - dnsmasq-full
      remove:
        - dnsmasq
    files:
      - path: /etc/motd
        contents: |
          This is a message of the day.

          This is another line in the MOTD.
```

The mechanism by which these files end up in the firmware is that
`openwrt-composer` writes them to disk and then passes them as the `FILES`
argument when invoking the OpenWRT image builder. 


#### Option 2: using the `config` section in the manifest

The `config` section of a firmware image specification is passed through
[NetJSONConfig](http://netjsonconfig.openwisp.org/en/latest/) to produce a set
of configuration files which are then included in the firmware image via the
`FILES` argument of the OpenWRT Image Builder.

A short (incomplete) example is shown below:

```yaml
firmwares:
  - target: lantiq
    sub_target: xrx200
    profile:  bt_homehub-v5a
    version: 18.06.1
    name: router
    packages:
      add:
        - dnsmasq-full
      remove:
        - dnsmasq
    config:
      interfaces:
        - name: "ppp0"
          type: "other"
          proto: "ppp"
          device: "/dev/usb/modem1"
          username: "user1"
          password: "pwd0123"
          keepalive: 3
          ipv6: True
```

Note: Since the NetJSONConfig specification allows the [inclusion of additional
files](http://netjsonconfig.openwisp.org/en/latest/backends/openwrt.html#including-additional-files),
in principle this removes the need for the simple `files` section described
above. However, the simplicity of the `files` method above is attractive, and so
we retain that functionality.



## Backends

Firmware building is done using [OpenWRT image
builders](https://openwrt.org/docs/guide-user/additional-software/imagebuilder)
running inside a container.

The approach taken is to create a container image for any required (target,
sub-target, profile) firmware combination containing the relevant OpenWRT image
builder. All of these (target, sub-target, profile) firmware builder images are
built from a common base image (currently based on Fedora 31 with the relevant
tools installed).

At present, the only container runtime supported is [Podman](https://podman.io),
but Docker support will be added in the near future.
