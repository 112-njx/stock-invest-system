cmake_minimum_required(VERSION 3.15)
project(cpp_analysis_service LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

file(GLOB_RECURSE SRC_FILES
        ${PROJECT_SOURCE_DIR}/src/*.cpp
)

add_executable(${PROJECT_NAME} ${SRC_FILES})

target_include_directories(${PROJECT_NAME} PRIVATE
        ${PROJECT_SOURCE_DIR}/third_party
        ${PROJECT_SOURCE_DIR}/src
)

# MySQL 8.0 Connector/C config

set(CPP_BACKTEST_HAS_MYSQL 0)

# 指向 MySQL Server 8.0 根目录
set(MYSQL_ROOT "C:/Program Files/MySQL/MySQL Server 8.0")

# 头文件
find_path(MYSQL_INCLUDE_DIR
        NAMES mysql.h
        PATHS "${MYSQL_ROOT}/include"
        NO_DEFAULT_PATH
)

# 库文件（Windows 下一般是 libmysql.lib）
find_library(MYSQL_CLIENT_LIBRARY
        NAMES libmysql
        PATHS "${MYSQL_ROOT}/lib"
        NO_DEFAULT_PATH
)

if (MYSQL_INCLUDE_DIR AND MYSQL_CLIENT_LIBRARY)

    message(STATUS "MySQL include: ${MYSQL_INCLUDE_DIR}")
    message(STATUS "MySQL lib: ${MYSQL_CLIENT_LIBRARY}")

    set(CPP_BACKTEST_HAS_MYSQL 1)

    target_include_directories(${PROJECT_NAME} PRIVATE ${MYSQL_INCLUDE_DIR})
    target_link_libraries(${PROJECT_NAME} PRIVATE ${MYSQL_CLIENT_LIBRARY})

    # 自动复制 DLL 到 exe 目录
    add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${MYSQL_ROOT}/lib/libmysql.dll"
            $<TARGET_FILE_DIR:${PROJECT_NAME}>
    )

    message(STATUS "MySQL 8.0 client ENABLED")

else()

    message(WARNING "MySQL 8.0 client NOT FOUND — backtest DB disabled")

endif()

target_compile_definitions(${PROJECT_NAME}
        PRIVATE CPP_BACKTEST_HAS_MYSQL=${CPP_BACKTEST_HAS_MYSQL}
)
# Windows config

if (WIN32)
    target_compile_definitions(${PROJECT_NAME} PRIVATE _WIN32_WINNT=0x0A00)
    target_link_libraries(${PROJECT_NAME} PRIVATE ws2_32)
endif()

if (MSVC)
    target_compile_options(${PROJECT_NAME} PRIVATE /W4)
else()
    target_compile_options(${PROJECT_NAME} PRIVATE -Wall -Wextra -Wpedantic)
endif()