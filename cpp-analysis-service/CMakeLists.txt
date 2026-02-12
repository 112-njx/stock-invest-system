cmake_minimum_required(VERSION 3.15)

# 项目名 & 语言
project(cpp_analysis_service LANGUAGES CXX)

# C++ 标准
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 输出目录
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

# 第三方库（header-only）

# cpp-httplib
include_directories(
        ${PROJECT_SOURCE_DIR}/third_party
)

# 项目源码
include_directories(
        ${PROJECT_SOURCE_DIR}/src
)

file(GLOB_RECURSE SRC_FILES
        ${PROJECT_SOURCE_DIR}/src/*.cpp
)

# 可执行程序
add_executable(${PROJECT_NAME}
        ${SRC_FILES}
)
# 平台相关配置
if (WIN32)
    # Windows 10+
    target_compile_definitions(${PROJECT_NAME} PRIVATE _WIN32_WINNT=0x0A00)
endif()

# 编译警告
if (MSVC)
    target_compile_options(${PROJECT_NAME} PRIVATE /W4)
else()
    target_compile_options(${PROJECT_NAME} PRIVATE -Wall -Wextra -Wpedantic)
endif()