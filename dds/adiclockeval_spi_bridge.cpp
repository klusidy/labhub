// "C:\mingw-w64\i686-12.2.0-posix-dwarf-rt_v10-rev0\mingw32\bin\g++.exe" ^
//  -m32 -O2 -static -static-libgcc -static-libstdc++ -s ^
//  -o adiclockeval_spi_bridge.exe adiclockeval_spi_bridge.cpp
// Define Windows version for SetDllDirectoryA (XP SP1+)
// C:\MinGW\bin\gcc.exe -m32 -lstdc++-static -o adiclockeval_spi_bridge.exe adiclockeval_spi_bridge.cpp
// C:\MinGW\bin\g++.exe -m32 -O2 -s -o adiclockeval_spi_bridge.exe adiclockeval_spi_bridge.cpp

#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0502
#endif

#include <windows.h>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <string>
#include <vector>
#include <algorithm>

// ---- DLL function types (stdcall as WinDLL in Python) ----
typedef void     (WINAPI *FindHardwareFunc)(uint32_t*, uint32_t*, int);
typedef uint32_t (WINAPI *GetVendorIDFunc)(int);
typedef uint32_t (WINAPI *GetProductIDFunc)(int);
typedef int      (WINAPI *SpiWriteFunc)(int, void*, int);
typedef int      (WINAPI *SetPortValueFunc)(int, uint32_t, uint32_t);

// Globals
static HMODULE           g_hDll = NULL;
static FindHardwareFunc  g_FindHardware  = NULL;
static GetVendorIDFunc   g_GetVendorID   = NULL;
static GetProductIDFunc  g_GetProductID  = NULL;
static SpiWriteFunc      g_SpiWrite      = NULL;
static SetPortValueFunc  g_SetPortValue  = NULL;

static void trim_crlf(std::string &s) {
    while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
}

static bool ieq(const char* a, const char* b) {
    for (; *a && *b; ++a, ++b) {
        char ca = (*a >= 'A' && *a <= 'Z') ? char(*a + 32) : *a;
        char cb = (*b >= 'A' && *b <= 'Z') ? char(*b + 32) : *b;
        if (ca != cb) return false;
    }
    return *a == *b;
}

static bool load_dll_and_symbols(const char* dll_fullpath) {
    // Add directory to DLL search path and load the DLL with altered path search
    char dll_dir[MAX_PATH];
    strncpy(dll_dir, dll_fullpath, sizeof(dll_dir) - 1);
    dll_dir[sizeof(dll_dir) - 1] = '\0';

    char* last_slash = strrchr(dll_dir, '\\');
    if (last_slash) *last_slash = '\0';

    if (!SetDllDirectoryA(dll_dir)) {
        // Non-fatal; dependent DLLs may still be found by LOAD_WITH_ALTERED_SEARCH_PATH
    }

    g_hDll = LoadLibraryExA(dll_fullpath, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!g_hDll) {
        DWORD e = GetLastError();
        std::fprintf(stderr, "ERROR: LoadLibraryExA failed (%lu)\n", e);
        if (e == ERROR_MOD_NOT_FOUND)
            std::fprintf(stderr, "Hint: missing dependency in the same folder as the target DLL.\n");
        else if (e == ERROR_BAD_EXE_FORMAT)
            std::fprintf(stderr, "Hint: arch mismatch (need 32-bit DLL).\n");
        return false;
    }

    auto need = [&](FARPROC p, const char* name)->bool {
        if (!p) std::fprintf(stderr, "ERROR: missing export: %s\n", name);
        return p != NULL;
    };

    g_FindHardware = (FindHardwareFunc)GetProcAddress(g_hDll, "FindHardware");
    g_GetVendorID  = (GetVendorIDFunc) GetProcAddress(g_hDll, "GetVendorID");
    g_GetProductID = (GetProductIDFunc)GetProcAddress(g_hDll, "GetProductID");
    g_SpiWrite     = (SpiWriteFunc)     GetProcAddress(g_hDll, "SpiWrite");
    g_SetPortValue = (SetPortValueFunc) GetProcAddress(g_hDll, "SetPortValue");

    bool ok = true;
    ok &= need((FARPROC)g_FindHardware, "FindHardware");
    ok &= need((FARPROC)g_GetVendorID,  "GetVendorID");
    ok &= need((FARPROC)g_GetProductID, "GetProductID");
    ok &= need((FARPROC)g_SpiWrite,     "SpiWrite");
    ok &= need((FARPROC)g_SetPortValue, "SetPortValue");
    return ok;
}

// Parse unsigned (dec or hex "0x..")
static bool parse_u32(const char* s, uint32_t &out) {
    char* end = nullptr;
    unsigned long v = std::strtoul(s, &end, 0);
    if (end == s || *end != '\0') return false;
    out = (uint32_t)v;
    return true;
}

// Join remaining tokens into a single string
static std::string join_tokens(const std::vector<std::string>& tok, size_t start) {
    std::string out;
    for (size_t i = start; i < tok.size(); ++i) {
        if (i != start) out.push_back(' ');
        out += tok[i];
    }
    return out;
}

// Parse hex bytes from either a blob or mixed separators / 0x prefixes.
// Accepts forms: "0102030C", "01 02 03 0C", "01:02:03:0C", "0x01 0x02 0x03 0x0C", "01-02,03;0C"
static bool parse_hex_bytes(const std::vector<std::string>& tokens, size_t start_index, std::vector<uint8_t>& out) {
    std::string s = join_tokens(tokens, start_index);

    // Normalize: remove spaces, commas, semicolons, colons, dashes
    s.erase(std::remove_if(s.begin(), s.end(), [](char c){
        return c==' ' || c=='\t' || c==',' || c==';' || c==':' || c=='-';
    }), s.end());

    // Replace any "0x" or "0X" with nothing
    std::string norm; norm.reserve(s.size());
    for (size_t i=0; i<s.size(); ) {
        if (i+1 < s.size() && s[i]=='0' && (s[i+1]=='x' || s[i+1]=='X')) {
            i += 2;
        } else {
            norm.push_back(s[i++]);
        }
    }

    if (norm.empty()) return false;
    if (norm.size() % 2 != 0) {
        // Odd number of nibbles -> prepend a '0'
        norm.insert(norm.begin(), '0');
    }

    out.clear();
    out.reserve(norm.size()/2);

    auto hexval = [](char c)->int {
        if (c>='0' && c<='9') return c-'0';
        if (c>='a' && c<='f') return 10 + (c-'a');
        if (c>='A' && c<='F') return 10 + (c-'A');
        return -1;
    };

    for (size_t i = 0; i < norm.size(); i += 2) {
        int hi = hexval(norm[i]);
        int lo = hexval(norm[i+1]);
        if (hi < 0 || lo < 0) return false;
        out.push_back((uint8_t)((hi<<4) | lo));
    }
    return true;
}

// Split a line into tokens by whitespace
static std::vector<std::string> split_ws(const std::string& line) {
    std::vector<std::string> out;
    const char* s = line.c_str();
    while (*s) {
        while (*s==' ' || *s=='\t') ++s;
        if (!*s) break;
        const char* b = s;
        while (*s && *s!=' ' && *s!='\t' && *s!='\r' && *s!='\n') ++s;
        out.emplace_back(b, s - b);
    }
    return out;
}

static void cmd_find_hardware(const std::vector<std::string>& t) {
    if (t.size() < 2) { std::printf("ERROR FIND_HARDWARE requires count\n"); return; }

    uint32_t count_u32=0;
    if (!parse_u32(t[1].c_str(), count_u32)) { std::printf("ERROR Invalid count\n"); return; }
    int count = (int)count_u32;
    if (count <= 0 || count > 64) { std::printf("ERROR Bad count (1..64)\n"); return; }

    // Prepare arrays (DLL will overwrite with found values)
    std::vector<uint32_t> vids(count, 0), pids(count, 0);

    // Optional VID/PID seed pairs
    size_t pairs = (t.size() > 2) ? (t.size() - 2) / 2 : 0;
    for (size_t i = 0; i < pairs && i < (size_t)count; ++i) {
        uint32_t v=0, p=0;
        if (!parse_u32(t[2 + 2*i].c_str(), v) || !parse_u32(t[2 + 2*i + 1].c_str(), p)) {
            std::printf("ERROR Invalid VID/PID at index %zu\n", i);
            return;
        }
        vids[i] = v; pids[i] = p;
    }

    g_FindHardware(vids.data(), pids.data(), count);

    std::printf("OK");
    for (int i = 0; i < count; ++i) std::printf(" %u %u", vids[i], pids[i]);
    std::printf("\n");
}

static void cmd_get_vendor_id(const std::vector<std::string>& t) {
    int dev_id = 0;
    if (t.size() >= 2) dev_id = (int)std::strtol(t[1].c_str(), nullptr, 0);
    uint32_t v = g_GetVendorID(dev_id);
    std::printf("OK %u\n", v);
}

static void cmd_get_product_id(const std::vector<std::string>& t) {
    int dev_id = 0;
    if (t.size() >= 2) dev_id = (int)std::strtol(t[1].c_str(), nullptr, 0);
    uint32_t v = g_GetProductID(dev_id);
    std::printf("OK %u\n", v);
}

static void cmd_set_port_value(const std::vector<std::string>& t) {
    if (t.size() < 4) { std::printf("ERROR SET_PORT_VALUE requires dev_id command value\n"); return; }
    int dev_id = (int)std::strtol(t[1].c_str(), nullptr, 0);
    uint32_t cmd=0, val=0;
    if (!parse_u32(t[2].c_str(), cmd) || !parse_u32(t[3].c_str(), val)) {
        std::printf("ERROR Bad command/value\n"); return;
    }
    int rc = g_SetPortValue(dev_id, cmd, val);
    std::printf("OK %d\n", rc);
}

static void cmd_spi_write_hex(const std::vector<std::string>& t) {
    if (t.size() < 3) { std::printf("ERROR SPI_WRITE_HEX dev_id <hexdata>\n"); return; }
    int dev_id = (int)std::strtol(t[1].c_str(), nullptr, 0);

    std::vector<uint8_t> bytes;
    if (!parse_hex_bytes(t, 2, bytes) || bytes.empty()) {
        std::printf("ERROR Bad hex payload\n"); return;
    }

    // reverse byte order so CLI order matches device expectation
    std::reverse(bytes.begin(), bytes.end());

    int rc = g_SpiWrite(dev_id, (void*)bytes.data(), (int)bytes.size());
    std::printf("OK %d\n", rc);
    std::fflush(stdout);
}


static void process_line(const std::string& line) {
    auto t = split_ws(line);
    if (t.empty()) { std::printf("ERROR Empty\n"); return; }

    if (ieq(t[0].c_str(), "PING")) {
        std::printf("OK PONG\n");
    } else if (ieq(t[0].c_str(), "FIND_HARDWARE")) {
        cmd_find_hardware(t);
    } else if (ieq(t[0].c_str(), "GET_VENDOR_ID")) {
        cmd_get_vendor_id(t);
    } else if (ieq(t[0].c_str(), "GET_PRODUCT_ID")) {
        cmd_get_product_id(t);
    } else if (ieq(t[0].c_str(), "SET_PORT_VALUE")) {
        cmd_set_port_value(t);
    } else if (ieq(t[0].c_str(), "SPI_WRITE_HEX")) {
        cmd_spi_write_hex(t);
    } else if (ieq(t[0].c_str(), "QUIT")) {
        std::printf("OK Goodbye\n");
        std::fflush(stdout);
        std::exit(0);
    } else {
        std::printf("ERROR Unknown\n");
    }
}

int main(int argc, char* argv[]) {
    // Unbuffered I/O for tight pipe interaction
    setvbuf(stdin,  nullptr, _IONBF, 0);
    setvbuf(stdout, nullptr, _IONBF, 0);
    setvbuf(stderr, nullptr, _IONBF, 0);

    if (argc != 2) {
        std::fprintf(stderr, "Usage: %s <folder_of_adiclockeval.dll>\n", argv[0]);
        return 1;
    }

    // Compose full DLL path (fixed filename per vendor package)
    char dll_path[MAX_PATH];
    DWORD attr = GetFileAttributesA(argv[1]);
    if (attr == INVALID_FILE_ATTRIBUTES || !(attr & FILE_ATTRIBUTE_DIRECTORY)) {
        std::fprintf(stderr, "ERROR: argument must be a directory containing adiclockeval.dll\n");
        return 1;
    }
    std::snprintf(dll_path, sizeof(dll_path), "%s\\adiclockeval.dll", argv[1]);

    if (!load_dll_and_symbols(dll_path)) return 1;
    std::fprintf(stderr, "INFO: bridge ready\n");

    // Loop
    std::string line;
    line.reserve(4096);
    char buf[4096];

    while (true) {
        if (!std::fgets(buf, sizeof(buf), stdin)) {
            std::fprintf(stderr, "INFO: stdin closed, exiting\n");
            break;
        }
        line.assign(buf);
        trim_crlf(line);
        if (!line.empty()) process_line(line);
    }

    if (g_hDll) FreeLibrary(g_hDll);
    return 0;
}
