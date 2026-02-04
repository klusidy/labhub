🧪You work in a lab. You have bunch of instruments connected to your PC. The laser is from National Instruments, the detector from Thorlabs, the acquisition board from Diligent, there is a custom-made signal generator and an Arduino for some reason. 

🛠️You would like to somehow automate things - sweep some variables, measure stuff, set everything as it was last month. Maybe use git.

🖥️You know some rudimentary python. Your colleguage prefer julia. Your supervisor uses MATLAB since Uni and other folks cling to LabView or Perl or R.

👉**You need LabHub** 👈

# Quick overview

The main goal of LabHub is to be **convenient**, **easy to use**, **robust** and **extensible** tool for lab automation. This is a quick overview for users/engineers/physisists/etc. There is more technical description on the [[Architecture]].

![[overview.png]]
## LabHub server
The core of everything is a LabHub *server* that communicates with various devices and provides a unified interface (API) for GUIs or scripting clients (even multiple clients).

After starting Labhub, an icon appears in the system tray. Green indicates that the server is up and running. There are only a few things to do with the server beyond starting and stopping it (and there is rarely a reason to stop it). You can explore the [[API]] of the server if you are curious (or a developer). ![[launcher_tray.png]]

## Configuration
There is a config file that tells the server what devices to expect. You may be wondering about how a [[Configuration]] works like or how to add support for a new device by writing custom [[Drivers]]

During startup (or after reload), the server attempts to connect to the devices specified in config and then it constructs specification for them.

### Device specification
Each device exposes "*properties*", "*commands*" and "*data sources*".
- *property* is a scalar value (think of a variable), 
	- either number, truth value or a string
	- it may or may not be changed
	- for example `voltage`, `position` or `room_temperature`
- *command* is something the device can do (think of a function)
	- it may (not) have parameters and may (not) return a result
	- usually more complex than getting/setting a single *property*
	- for example`start_pumping` or `home_stage`
- *data source* is something that generates large amound of data
	- on-demand or continuously
	- often with associated plot
	- for example `time_series` or `power_spectrum`

### Web GUI
The server comes with a rudimentary *Web GUI* – basically a list of devices and their *properties*, *commands* and *data sources*. It is intened mostly as a reference for scripting but for basic tuning/setup/visual feedback it should do just fine.![[general_gui.png]]

### Synchronization
The LabHub server can serve multiple connected clients. Each client has access to the same devices and can interact with them at the same time. The server notifies all clients when something changes so that everyone can stay up-to-date. On the one hand, you can monitor what is going on with what device. On the other hand, you may unwittingly change something mid-script and mess things up. Just be aware that there is no preferential treatment between clients.

### Scripting clients
The web GUI mentioned above is one such client. Then there are so-called "scripting clients" for python and julia (matlab is planned). These clients look like an ordinary python (julia, matlab) package that you import and after connecting to the server, all devices and their *properties*, *commands* and *data sources* are available straightaway. You can use them from jupyter notebook as well. It looks like this:

```python
import client.python as lhc

lhc.connect("127.0.0.1", 8212) # connect to local machine at the labhub port
lhc.dummy_01.foo = 0.42        # set a property 'foo' on device 'dummy_01'
print(lhc.dummy_01.foo)        # read and print the same property
lhc.dummy_01.bar()             # call command 'bar()' on the same device
```

And that's it – you're set to go! Next, check out the step-by-step [[docs/Installation]] or the list of currently [[Supported devices]] or – if you're device is missing – guide on how to [[Add support for a new device]] (its not that difficult). There is also more detailed technical description of the [[Architecture]].

# What about package X?

Yes, I'm aware that there are several python packages that are trying to address the same problem. 
- PyMeasure
- PycroManager
- ...
However, I haven't found one that would support scripting in multiple languages, had synchronization between live GUI/scripts or one that would support the devices in our lab. Furthermore I don't find any of them to be as convenient, easy to use, robust or extensible as I'd like🤷 (also it was kind of fun 🙂)

That being said, I plan to re-use parts of these packages to expand the list of supported devices at some point.
# Contribution

LabHub will become more usable and (hopefully) wide-spread with the number of supported devices. Contributing new drivers is strongly encouraged and more than welcomed! There is currently no procedure in place beyond "open a pull request". I'll do my best for code reviews but without having access to the device itself, there is only so much I can do. I'm not yet sure how to deal with growing dependencies with new drivers. I guess I'll make it up as I go🙂 (likely an "installation guide" for each device)

I'm open to other ideas/suggestions/improvements/questions as well (new clients, tests, long-term logging, anything). Open a github issue and I'll try to respond.

I have no capacity to add support for your device for free (but do get in touch if you're willing to pay 💰). 
# Attribution
If you've used LabHub in your scientific endeavours, please include the following attribution:
TODO
# Contact
The LabHub package is being developed by the levitation photonics group at the [Institute of Scientific Instruments](isibrno.cz) of the Czech Academy of Sciences, contact email klusacek@isibrno.cz
