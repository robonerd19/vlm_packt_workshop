cmake_minimum_required(VERSION 3.8)
project(go2_warehouse_world)

find_package(ament_cmake REQUIRED)

ament_environment_hooks("${CMAKE_CURRENT_SOURCE_DIR}/hooks/go2_warehouse_world.sh.in")

install(DIRECTORY worlds models LICENSE README.md DESTINATION share/${PROJECT_NAME})

ament_package()
