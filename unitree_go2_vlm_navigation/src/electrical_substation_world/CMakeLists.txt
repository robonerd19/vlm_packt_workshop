cmake_minimum_required(VERSION 3.8)
project(electrical_substation_world)

find_package(ament_cmake REQUIRED)

ament_environment_hooks("${CMAKE_CURRENT_SOURCE_DIR}/hooks/electrical_substation_world.sh.in")

install(
  DIRECTORY worlds models
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
