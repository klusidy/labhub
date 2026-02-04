Labhub comes with a general (auto-generated) web based GUI `http://127.0.0.1/ui`

It is ideal for live tuning and tinkering but also handy as a reference of connected devices and their capabilities. 

![[general_gui.png]]
On the left, there is a collapsible tree listing all connected devices, and their data streams, properties and commands. The middle provides a detailed view on currently selected items. It is also possible to put selected items to the right on a "shelf" so that perticular properties/commands remain accessible when browsing a different device.

## Admin GUIs
There are two UIs for managing the [[Configuration]] of a running server. The Device configuration at `http://127.0.0.1/devices` shows all the devices (even unconnected ones) together with their connection info. It is also possible to add/remove a device or to attempt a reconnect with different settings.

![[device_gui.png]]

The Profile configuration allows convenient way to setting up a profile policies (whether a value should/not be restored upon startup).

![[profile_gui.png]]
## Custom GUIs

Full support for custom GUIs is not yet supported. The idea is that the Labhub server can easily serve several similar web-based applications but proper integration and automatic discovery is a bit tricky.

For now, there is a custom GUI for a picoscope device - we've found that an oscilloscope cannot be managed by auto-generated GUI and more convenient approach is necessary. It is accessible at `http://127.0.0.1/picoscope` (if a picoscope device is present)

![[picoscope_gui.png]]

However, it shall be fairly straightforward to implement similar custom GUIs in any framework of your choosing. All you need is the ability to communicate over http/websocket. See the API docs at `http://127.0.0.1/docs` or look at `gui/custom/picoscope` for inspiration.