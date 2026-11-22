/*
 * CLIPOS -- self-extracting Windows installer launcher.
 *
 * The frozen application is appended to this executable as a ZIP archive.
 * At startup the launcher:
 *
 *   1. finds its own path,
 *   2. reads the trailer that records where the payload starts,
 *   3. extracts the payload into the install directory,
 *   4. creates the Start-menu and desktop shortcuts,
 *   5. registers the uninstaller, and
 *   6. launches the application.
 *
 * It is compiled to a native Win32 PE executable with zig cc (or any mingw
 * compiler), so a Windows installer can be produced without Inno Setup or
 * NSIS being installed on the build machine.
 *
 * The payload is a ZIP.  Rather than linking against zlib, the launcher
 * shells out to the PowerShell that ships with every supported Windows
 * release to expand the archive; that keeps the executable tiny and avoids
 * a third-party dependency.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define APP_NAME     "CLIPOS"
#define APP_EXE      "CLIPOS.exe"
#define PAYLOAD_NAME "clipos-payload.zip"
#define TRAILER_SIG  "CLIPOSPAY"

/* The last 16 bytes of the file: a signature and the payload length. */
typedef struct {
    char     magic[8];   /* "CLIPOSPAY" */
    DWORD    length;     /* payload size in bytes      */
    DWORD    reserved;   /* keeps the struct 16 bytes  */
} payload_trailer;

static void app_dir(char *out, size_t size)
{
    const char *base = getenv("LOCALAPPDATA");
    if (!base || !*base) base = getenv("USERPROFILE");
    if (!base || !*base) base = "C:\\Users\\Public";
    snprintf(out, size, "%s\\Programs\\%s", base, APP_NAME);
}

static void app_path(char *out, size_t size)
{
    char dir[MAX_PATH];
    app_dir(dir, sizeof(dir));
    snprintf(out, size, "%s\\%s", dir, APP_EXE);
}

static void message(const char *text)
{
    MessageBoxA(NULL, text, APP_NAME, MB_OK | MB_ICONINFORMATION);
}

static void error_message(const char *text)
{
    MessageBoxA(NULL, text, APP_NAME " — installation problem",
                 MB_OK | MB_ICONERROR);
}

/* Run a command and wait for it.  Returns the exit code. */
static int run_command(const char *command)
{
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    DWORD code = 1;

    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (!CreateProcessA(NULL, (LPSTR)command, NULL, NULL, FALSE,
                       0, NULL, NULL, &si, &pi)) {
        return 1;
    }
    WaitForSingleObject(pi.hProcess, INFINITE);
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return (int)code;
}

int main(void)
{
    char self[MAX_PATH];
    char tempDir[MAX_PATH];
    char zipPath[MAX_PATH];
    char extractDir[MAX_PATH];
    char installDir[MAX_PATH];
    char appExe[MAX_PATH];
    char command[8192];
    HANDLE file;
    DWORD size;
    DWORD read = 0;
    payload_trailer trailer;

    if (!GetModuleFileNameA(NULL, self, MAX_PATH)) {
        error_message("CLIPOS could not work out its own location.");
        return 1;
    }

    file = CreateFileA(self, GENERIC_READ, FILE_SHARE_READ, NULL,
                       OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) {
        error_message("CLIPOS could not open the installer file.");
        return 1;
    }

    size = GetFileSize(file, NULL);
    if (size < (DWORD)sizeof(payload_trailer)) {
        CloseHandle(file);
        error_message("This installer is incomplete. Please download it again.");
        return 1;
    }

    SetFilePointer(file, size - sizeof(payload_trailer), NULL, FILE_BEGIN);
    if (!ReadFile(file, &trailer, sizeof(trailer), &read, NULL) ||
        read != sizeof(trailer) ||
        memcmp(trailer.magic, TRAILER_SIG, 8) != 0) {
        CloseHandle(file);
        error_message("This installer is damaged. Please download it again.");
        return 1;
    }

    if (trailer.length == 0 || trailer.length > size - sizeof(payload_trailer)) {
        CloseHandle(file);
        error_message("This installer is damaged. Please download it again.");
        return 1;
    }

    /* Copy the payload out into a temporary ZIP. */
    if (!GetTempPathA(MAX_PATH, tempDir)) {
        CloseHandle(file);
        error_message("CLIPOS could not create a temporary folder.");
        return 1;
    }
    snprintf(zipPath, sizeof(zipPath), "%s%s", tempDir, PAYLOAD_NAME);

    SetFilePointer(file, size - sizeof(payload_trailer) - trailer.length,
                   NULL, FILE_BEGIN);

    HANDLE out = CreateFileA(zipPath, GENERIC_WRITE, 0, NULL,
                             CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (out == INVALID_HANDLE_VALUE) {
        CloseHandle(file);
        error_message("CLIPOS could not write the temporary installer file.");
        return 1;
    }

    unsigned char *buffer = (unsigned char *)malloc(65536);
    DWORD remaining = trailer.length;
    int ok = buffer != NULL;
    while (ok && remaining > 0) {
        DWORD chunk = remaining > 65536 ? 65536 : remaining;
        DWORD got = 0;
        if (!ReadFile(file, buffer, chunk, &got, NULL) || got == 0) {
            ok = 0;
            break;
        }
        DWORD wrote = 0;
        if (!WriteFile(out, buffer, got, &wrote, NULL) || wrote != got) {
            ok = 0;
            break;
        }
        remaining -= got;
    }
    free(buffer);
    CloseHandle(out);
    CloseHandle(file);

    if (!ok) {
        DeleteFileA(zipPath);
        error_message("CLIPOS could not read its own installer data.");
        return 1;
    }

    /* Expand the payload next to the ZIP, then move it into place. */
    snprintf(extractDir, sizeof(extractDir), "%sclipos_extract", tempDir);
    snprintf(command, sizeof(command),
             "powershell -NoProfile -ExecutionPolicy Bypass -Command "
             "\"$ErrorActionPreference='Stop';"
             "if (Test-Path '%s') { Remove-Item -Recurse -Force '%s' };"
             "Expand-Archive -LiteralPath '%s' -DestinationPath '%s' -Force\"",
             extractDir, extractDir, zipPath, extractDir);
    if (run_command(command) != 0) {
        DeleteFileA(zipPath);
        error_message("CLIPOS could not unpack the application files.");
        return 1;
    }
    DeleteFileA(zipPath);

    app_dir(installDir, sizeof(installDir));
    app_path(appExe, sizeof(appExe));

    /* Move the extracted application into the install directory. */
    snprintf(command, sizeof(command),
             "powershell -NoProfile -ExecutionPolicy Bypass -Command "
             "\"$ErrorActionPreference='Stop';"
             "New-Item -ItemType Directory -Force -Path '%s' | Out-Null;"
             "Copy-Item -Recurse -Force '%s\\*' '%s\\'\"",
             installDir, extractDir, installDir);
    if (run_command(command) != 0) {
        error_message("CLIPOS could not copy the application into place.");
        return 1;
    }
    RemoveDirectoryA(extractDir);

    /* Shortcuts and the uninstall entry. */
    snprintf(command, sizeof(command),
             "powershell -NoProfile -ExecutionPolicy Bypass -Command "
             "\"$ErrorActionPreference='Stop';"
             "$ws=New-Object -ComObject WScript.Shell;"
             "$sp=[Environment]::GetFolderPath('Programs');"
             "$dir=Join-Path $sp '%s';"
             "New-Item -ItemType Directory -Force -Path $dir | Out-Null;"
             "$l=$ws.CreateShortcut((Join-Path $dir '%s.lnk'));"
             "$l.TargetPath='%s'; $l.Save();"
             "$l2=$ws.CreateShortcut((Join-Path $dir 'Uninstall %s.lnk'));"
             "$l2.TargetPath='%s'; $l2.Save();"
             "$l3=$ws.CreateShortcut((Join-Path [Environment]::GetFolderPath('Desktop') '%s.lnk'));"
             "$l3.TargetPath='%s'; $l3.Save();"
             "New-Item -ItemType Directory -Force -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\%s' | Out-Null;"
             "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\%s' -Name 'DisplayName' -Value '%s';"
             "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\%s' -Name 'UninstallString' -Value 'cmd /c rmdir /s /q \\\"%s\\\"';"
             "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\%s' -Name 'DisplayVersion' -Value '1.0.0';"
             "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\%s' -Name 'Publisher' -Value 'CLIPOS Studio';"
             "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\%s' -Name 'NoModify' -Value 1;\"",
             APP_NAME, APP_NAME, appExe, APP_NAME, appExe, APP_NAME, appExe,
             APP_NAME, APP_NAME, APP_NAME, APP_NAME, installDir, APP_NAME,
             APP_NAME);
    run_command(command);

    message(APP_NAME " was installed successfully.\n\n"
           "It is in your Start menu, and there is a shortcut on your desktop.\n\n"
           "You can remove it at any time with "
           "Settings > Apps > Installed apps > " APP_NAME ".");

    /* Start the application. */
    ShellExecuteA(NULL, "open", appExe, NULL, NULL, SW_SHOWNORMAL);
    return 0;
}
