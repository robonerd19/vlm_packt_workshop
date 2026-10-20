# Electrical substation world

This package adds the Robotnik Automation electrical substation environment
to the Go2 workspace. It includes the world and its local static models so
they are available without downloading models when Gazebo starts.

Source: [RobotnikAutomation/robotnik_gazebo_worlds](https://github.com/RobotnikAutomation/robotnik_gazebo_worlds),
`electrical_substation_world`, commit
`92dba6aa0a25fe24eded378c01c945e0c558f533`.

The source package manifest identifies BSD licensing and its launch source
includes a BSD notice. The upstream README also mentions Apache 2.0, but the
referenced LICENSE file is absent from that source revision. This package keeps
the BSD notice and upstream attribution; the world and models have not been
relicensed.

The upstream worker actor was omitted because it referenced an animation mesh
hosted separately on Gazebo Fuel. The remaining world assets are stored locally.
