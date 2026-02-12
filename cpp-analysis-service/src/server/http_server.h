#pragma once
#include <string>

class HttpServer {
public:
    void start(const std::string& host, int port);
};