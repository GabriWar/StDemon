#!/usr/bin/env python3
# stdutil.py - Process utility script

import os
import platform
import subprocess
import re
import sys
import time
import select
import curses

# ANSI color codes for non-TUI parts
RESET, BOLD = "\033[0m", "\033[1m"
RED, GREEN, YELLOW = "\033[31m", "\033[32m", "\033[33m"
BLUE, MAGENTA, CYAN, WHITE = "\033[34m", "\033[35m", "\033[36m", "\033[37m"

def get_all_processes():
    """Get a list of all running processes with their PIDs and command names."""
    processes = []
    system = platform.system()
    
    try:
        if system == "Linux":
            output = subprocess.check_output(['ps', 'aux'], text=True)
            lines = output.strip().split('\n')[1:]  # Skip header line
            for line in lines:
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    processes.append((parts[1], parts[10]))  # pid, cmd
        elif system == "Windows":
            output = subprocess.check_output('tasklist /fo csv /nh', shell=True, text=True)
            for line in output.strip().split('\n'):
                parts = line.strip().strip('"').split('","')
                if len(parts) >= 2:
                    processes.append((parts[1], parts[0]))  # pid, name
        else:
            print(f"Unsupported operating system: {system}")
    except Exception as e:
        print(f"Error getting process list: {str(e)}")
    
    return processes

def search_processes(processes, search_term):
    """Search for processes matching the given term (case-insensitive)."""
    search_term = search_term.lower()
    return [proc for proc in processes if search_term in proc[0].lower() or search_term in proc[1].lower()]

def get_proc_info(pid):
    """Get detailed information about a process from /proc/ filesystem on Linux."""
    if platform.system() != "Linux":
        return {"error": "This function is only available on Linux"}
    
    info = {}
    proc_path = f"/proc/{pid}"
    
    if not os.path.exists(proc_path):
        return {"error": f"Process {pid} no longer exists"}
    
    try:
        # Basic info - status
        if os.path.exists(f"{proc_path}/status"):
            with open(f"{proc_path}/status", "r") as f:
                for line in f.read().splitlines():
                    if ":" in line:
                        key, value = line.split(":", 1)
                        info[key.strip()] = value.strip()
        
        # Command line
        if os.path.exists(f"{proc_path}/cmdline"):
            with open(f"{proc_path}/cmdline", "r") as f:
                info["cmdline"] = f.read().replace('\0', ' ').strip()
        
        # Memory info
        if os.path.exists(f"{proc_path}/statm"):
            with open(f"{proc_path}/statm", "r") as f:
                statm = f.read().strip().split()
                if len(statm) >= 7:
                    page_size = os.sysconf("SC_PAGE_SIZE")
                    info["memory"] = {
                        "total_program_size": int(statm[0]) * page_size / 1024,  # KB
                        "resident_set_size": int(statm[1]) * page_size / 1024,   # KB
                        "shared_pages": int(statm[2]) * page_size / 1024,        # KB
                        "text": int(statm[3]) * page_size / 1024,                # KB
                        "data_stack": int(statm[5]) * page_size / 1024           # KB
                    }
        
        # CPU info
        if os.path.exists(f"{proc_path}/stat"):
            with open(f"{proc_path}/stat", "r") as f:
                stat_parts = f.read().strip().split()
                if len(stat_parts) >= 44:
                    info["cpu"] = {
                        "user_time": float(stat_parts[13]) / os.sysconf("SC_CLK_TCK"),
                        "system_time": float(stat_parts[14]) / os.sysconf("SC_CLK_TCK"),
                        "start_time": float(stat_parts[21]) / os.sysconf("SC_CLK_TCK")
                    }
                    
                    # Calculate process uptime
                    with open("/proc/uptime", "r") as uptime_f:
                        uptime = float(uptime_f.read().split()[0])
                        start_seconds_since_boot = float(stat_parts[21]) / os.sysconf("SC_CLK_TCK")
                        info["uptime"] = uptime - start_seconds_since_boot
        
        # File descriptors
        fd_path = f"{proc_path}/fd"
        if os.path.exists(fd_path):
            try:
                fd_list = os.listdir(fd_path)
                info["fd_count"] = len(fd_list)
                info["fd_details"] = []
                for fd in fd_list[:10]:  # Limit to first 10 for performance
                    try:
                        target = os.readlink(f"{fd_path}/{fd}")
                        info["fd_details"].append((fd, target))
                    except: pass
            except PermissionError:
                info["fd_count"] = "(Permission denied)"
                
        # IO statistics
        if os.path.exists(f"{proc_path}/io"):
            try:
                with open(f"{proc_path}/io", "r") as f:
                    io_info = {}
                    for line in f.read().splitlines():
                        if ":" in line:
                            key, value = line.split(":", 1)
                            io_info[key.strip()] = value.strip()
                    info["io"] = io_info
            except:
                info["io"] = "(Unable to read I/O statistics)"
    except Exception as e:
        info["error"] = f"Error reading process information: {str(e)}"
    
    return info

def monitor_io_streams(pid):
    """Monitor stdout of a process on Linux using strace. Allow writing to stdin if possible."""
    if platform.system() != "Linux":
        print("This functionality is only available on Linux.")
        return
    
    # Check if strace is installed
    try:
        subprocess.run(['which', 'strace'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError:
        print("Error: strace is not installed. Please install it")
        input("\nPress Enter to continue...")
        return
    
    # Check if process exists
    proc_path = f"/proc/{pid}"
    if not os.path.exists(proc_path):
        print(f"Process {pid} does not exist.")
        return
    
    print(f"Monitoring stdout for process {pid} using strace...")
    print("Type text and press Enter to send to the process's stdin (may not work for all processes)")
    print("Press Ctrl+C to stop monitoring.")
    stdin_path = f"{proc_path}/fd/0"
    
    try:
        cmd = ["strace", "-p", str(pid), "-e", "trace=write", "-s", "1024", "-f"]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 universal_newlines=True, bufsize=1)
        
        while True:
            # Check if the process is still alive
            if not os.path.exists(proc_path):
                print("\n[!] The monitored process has exited.")
                break
            
            # Non-blocking read from strace output
            if process.stdout:
                line = process.stdout.readline()
                if line:
                    if "write(1," in line:
                        match = re.search(r'write\(1, "([^"]*)"', line)
                        if match:
                            content = match.group(1)
                            content = content.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')
                            content = re.sub(r'\\x[0-9a-f]{2}', '', content)
                            print(content, end='', flush=True)
                    elif "attach" in line or "detach" in line or "exit" in line or "signal" in line:
                        print(f"[strace] {line.strip()}")
            
            # Prompt for user input to send to stdin
            rlist, _, _ = select.select([sys.stdin], [], [], 1)
            if rlist:
                user_input = sys.stdin.readline().rstrip("\n")
                if user_input and os.path.exists(stdin_path):
                    try:
                        with open(stdin_path, "w") as f:
                            f.write(user_input + "\n")
                            f.flush()
                        print(f"[Sent to stdin: {user_input}]")
                    except Exception as e:
                        print(f"[Error writing to stdin: {e}]")
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")
    except subprocess.SubprocessError as e:
        print(f"\nError during monitoring: {str(e)}")
    finally:
        if 'process' in locals():
            try:
                process.terminate()
                process.wait(timeout=2)
            except:
                try: process.kill()
                except: pass
        
        # If process died, pause before returning
        if not os.path.exists(proc_path):
            input("Press Enter to return...")

def get_section_content(proc_path, section_id):
    """Get content for an advanced info section."""
    content = []
    if section_id == "maps":
        maps_path = f"{proc_path}/maps"
        if os.path.exists(maps_path):
            try:
                with open(maps_path) as f:
                    for line in f:
                        content.append(line.rstrip())
            except Exception as e:
                content.append(f"Error reading maps: {e}")
        else:
            content.append("maps not available")
            
    elif section_id == "fd":
        fd_path = f"{proc_path}/fd"
        if os.path.exists(fd_path):
            try:
                fds = os.listdir(fd_path)
                for fd in fds:
                    try:
                        target = os.readlink(f"{fd_path}/{fd}")
                        content.append(f"fd {fd}: {target}")
                    except Exception as e:
                        content.append(f"fd {fd}: Error: {e}")
            except Exception as e:
                content.append(f"Error reading fd: {e}")
        else:
            content.append("fd not available")
            
    elif section_id == "cwd":
        cwd_path = f"{proc_path}/cwd"
        try:
            content.append(os.readlink(cwd_path))
        except Exception as e:
            content.append(f"Error: {e}")
            
    elif section_id == "exe":
        exe_path = f"{proc_path}/exe"
        try:
            content.append(os.readlink(exe_path))
        except Exception as e:
            content.append(f"Error: {e}")
            
    elif section_id == "limits":
        limits_path = f"{proc_path}/limits"
        if os.path.exists(limits_path):
            try:
                with open(limits_path) as f:
                    for line in f:
                        content.append(line.rstrip())
            except Exception as e:
                content.append(f"Error reading limits: {e}")
        else:
            content.append("limits not available")
    
    return content

def main():
    """Main function for the process utility."""
    def tui_app(stdscr):
        # Initialize colors
        curses.start_color()
        curses.use_default_colors()
        for i in range(1, 8):
            curses.init_pair(i, i, -1)
        
        # TUI advanced info with collapsible sections
        def show_advanced_info_tui(pid):
            proc_path = f"/proc/{pid}"
            if not os.path.exists(proc_path):
                try:
                    stdscr.clear()
                    stdscr.addstr(0, 0, f"Process {pid} no longer exists.", curses.color_pair(1))
                    stdscr.addstr(2, 0, "Press any key to return...", curses.color_pair(7))
                    stdscr.refresh()
                    stdscr.getch()
                except curses.error:
                    pass
                return
            
            # Define sections
            sections = [
                ("Memory Maps", "maps"),
                ("Open Files/Sockets", "fd"),
                ("Current Working Directory", "cwd"),
                ("Executable Path", "exe"),
                ("Resource Limits", "limits")
            ]
            collapsed = [False] * len(sections)
            selected_idx = 0
            scroll_pos = 0
            max_lines = {}  # Store max lines for each section
            section_content = {}  # Cache for section content
            
            # Initialize content for all sections
            for _, section_id in sections:
                content = get_section_content(proc_path, section_id)
                section_content[section_id] = content
                max_lines[section_id] = len(content)
            
            def draw():
                try:
                    stdscr.clear()
                    h, w = stdscr.getmaxyx()
                    
                    # Draw title
                    title = f"=== Advanced Info for PID {pid} ==="
                    stdscr.addstr(0, (w - len(title)) // 2, title, curses.A_BOLD | curses.color_pair(6))
                    
                    y = 2
                    # Draw sections
                    for i, (section_name, section_id) in enumerate(sections):
                        if y >= h-2:
                            break
                            
                        # Draw section header
                        prefix = "[+]" if collapsed[i] else "[-]"
                        if i == selected_idx:
                            stdscr.addstr(y, 0, f"{prefix} {section_name}", curses.A_REVERSE | curses.color_pair(3))
                        else:
                            stdscr.addstr(y, 0, f"{prefix} {section_name}", curses.A_BOLD | curses.color_pair(3))
                        y += 1
                        
                        # Draw section content if not collapsed
                        if not collapsed[i]:
                            content = section_content[section_id]
                            content_scroll = 0 if i != selected_idx else scroll_pos
                            
                            # Calculate visible lines for this section
                            visible_lines = min(len(content) - content_scroll, h - y - 2)
                            if visible_lines <= 0:
                                continue
                                
                            # Draw content with scroll offset
                            for line_idx in range(content_scroll, content_scroll + visible_lines):
                                if line_idx >= len(content) or y >= h-2:
                                    break
                                    
                                line = content[line_idx]
                                
                                # Apply different colors based on content type
                                if section_id == "maps":
                                    parts = line.split()
                                    if len(parts) >= 1:
                                        addr_part = parts[0].split("-")
                                        if len(addr_part) == 2:
                                            # Color the address range
                                            addr_str = f"{addr_part[0]}-{addr_part[1]}"
                                            stdscr.addstr(y, 2, addr_str, curses.color_pair(6))
                                            if len(parts) > 1:
                                                perm = parts[1]
                                                # Color permissions with different colors
                                                pos = len(addr_str) + 3
                                                perm_color = curses.color_pair(2)  # Default green
                                                if 'w' in perm:
                                                    perm_color = curses.color_pair(1)  # Red if writable
                                                stdscr.addstr(y, pos, perm, perm_color)
                                                
                                                # Show rest of the line
                                                if len(parts) > 2:
                                                    rest = " ".join(parts[2:])
                                                    if "so" in rest or ".so" in rest:
                                                        # Highlight libraries
                                                        stdscr.addstr(y, pos + len(perm) + 1, rest, curses.color_pair(5))
                                                    else:
                                                        stdscr.addstr(y, pos + len(perm) + 1, rest, curses.color_pair(7))
                                    else:
                                        stdscr.addstr(y, 2, line, curses.color_pair(7))
                                elif section_id == "fd":
                                    if line.startswith("fd "):
                                        # Highlight fd number
                                        colon_pos = line.find(":")
                                        if colon_pos != -1:
                                            fd_num = line[3:colon_pos]
                                            stdscr.addstr(y, 2, f"fd {fd_num}", curses.color_pair(6))
                                            rest = line[colon_pos:]
                                            
                                            # Color based on fd target type
                                            color = curses.color_pair(7)  # Default white
                                            if "socket" in rest:
                                                color = curses.color_pair(5)  # Magenta for sockets
                                            elif "pipe" in rest:
                                                color = curses.color_pair(3)  # Yellow for pipes
                                            elif "/dev/" in rest:
                                                color = curses.color_pair(4)  # Blue for devices
                                            elif "Error" in rest:
                                                color = curses.color_pair(1)  # Red for errors
                                            else:
                                                color = curses.color_pair(2)  # Green for files
                                                
                                            stdscr.addstr(y, 2 + len(f"fd {fd_num}"), rest, color)
                                        else:
                                            stdscr.addstr(y, 2, line, curses.color_pair(7))
                                    else:
                                        stdscr.addstr(y, 2, line, curses.color_pair(7))
                                elif section_id in ["cwd", "exe"]:
                                    stdscr.addstr(y, 2, line, curses.color_pair(2))
                                elif section_id == "limits":
                                    if "unlimited" in line:
                                        stdscr.addstr(y, 2, line, curses.color_pair(2))
                                    else:
                                        stdscr.addstr(y, 2, line, curses.color_pair(7))
                                else:
                                    stdscr.addstr(y, 2, line, curses.color_pair(7))
                                    
                                y += 1
                                
                            # Show scroll indicator if needed
                            if len(content) > visible_lines:
                                if content_scroll > 0 and content_scroll + visible_lines < len(content):
                                    stdscr.addstr(y, w-10, "↕ more ↕", curses.color_pair(3))
                                elif content_scroll > 0:
                                    stdscr.addstr(y, w-10, "↑ more ↑", curses.color_pair(3))
                                elif content_scroll + visible_lines < len(content):
                                    stdscr.addstr(y, w-10, "↓ more ↓", curses.color_pair(3))
                                y += 1
                            
                        y += 1  # Add spacing after section
                        
                    # Draw footer
                    footer = "Up/Down:move, Space:expand/collapse, PgUp/PgDn:scroll, q:return"
                    if h > y + 1:
                        stdscr.addstr(h-1, 0, footer, curses.color_pair(7))
                        
                    stdscr.refresh()
                    
                except curses.error:
                    # Handle terminal size errors
                    stdscr.clear()
                    stdscr.refresh()
            
            # Main loop
            while True:
                draw()
                key = stdscr.getch()
                
                if key in (ord('q'), 27):  # q or ESC - quit
                    break
                elif key in (curses.KEY_UP, ord('k')):  # Up arrow - move selection up
                    if selected_idx > 0:
                        selected_idx -= 1
                        scroll_pos = 0  # Reset scroll position when changing selection
                elif key in (curses.KEY_DOWN, ord('j')):  # Down arrow - move selection down
                    if selected_idx < len(sections) - 1:
                        selected_idx += 1
                        scroll_pos = 0  # Reset scroll position when changing selection
                elif key in (curses.KEY_ENTER, 10, 13, ord(' ')):  # Enter/Space - toggle collapse
                    collapsed[selected_idx] = not collapsed[selected_idx]
                    scroll_pos = 0  # Reset scroll position when collapsing/expanding
                elif key == curses.KEY_NPAGE:  # Page Down - scroll down
                    if not collapsed[selected_idx]:
                        section_id = sections[selected_idx][1]
                        content_length = max_lines[section_id]
                        scroll_pos = min(scroll_pos + 5, content_length - 1)
                elif key == curses.KEY_PPAGE:  # Page Up - scroll up
                    if not collapsed[selected_idx]:
                        scroll_pos = max(0, scroll_pos - 5)
        
        # Process details screen
        def show_process_details(pid, cmd):
            proc_info = get_proc_info(pid)
            if "error" in proc_info:
                stdscr.clear()
                try:
                    stdscr.addstr(0, 0, proc_info["error"], curses.color_pair(1))
                    stdscr.addstr(2, 0, "Press any key to return...", curses.color_pair(3))
                    stdscr.refresh()
                    stdscr.getch()
                except curses.error:
                    pass
                return
                
            # Section order and keys
            sections = [
                ("General Info", ["Name", "State", "Tgid", "Pid", "PPid", "Uid", "Gid"]),
                ("Memory Usage", ["VmSize", "VmRSS", "VmSwap", "memory"]),
                ("CPU Usage", ["cpu", "uptime"]),
                ("Command Line", ["cmdline"]),
                ("File Descriptors", ["fd_count", "fd_details"]),
                ("I/O Statistics", ["io"]),
                ("Threads", ["Threads"]),
            ]
            collapsed = [False]*len(sections)
            menu = ["Refresh information", "Monitor stdout (using strace)", 
                   "Advanced info (memory maps, open files, etc)", "Return to main menu"]
            selected_section = 0
            selected_menu = 0
            mode = "sections"  # or "menu"
            
            while True:
                try:
                    stdscr.clear()
                    h, w = stdscr.getmaxyx()
                    stdscr.addstr(0, 0, f"=== Process Details for PID {pid} ===", curses.A_BOLD | curses.color_pair(6))
                    
                    # Colorize command text
                    stdscr.addstr(1, 0, "Command: ", curses.color_pair(3))
                    cmdlen = w - 10 if len(cmd) > w - 10 else len(cmd)
                    stdscr.addstr(1, 9, cmd[:cmdlen] + ("..." if len(cmd) > cmdlen else ""), curses.color_pair(2))
                    
                    y = 3
                    for i, (title, keys) in enumerate(sections):
                        if y >= h-1: break
                        
                        prefix = "[+]" if collapsed[i] else "[-]"
                        section_color = curses.color_pair(4)  # Blue for sections
                        
                        # Change color based on section type
                        if "Memory" in title:
                            section_color = curses.color_pair(5)  # Magenta for memory
                        elif "CPU" in title:
                            section_color = curses.color_pair(3)  # Yellow for CPU
                        elif "File" in title or "I/O" in title:
                            section_color = curses.color_pair(6)  # Cyan for I/O and files
                        
                        if mode == "sections" and i == selected_section:
                            stdscr.addstr(y, 0, f"{prefix} {title}", curses.A_REVERSE | section_color)
                        else:
                            stdscr.addstr(y, 0, f"{prefix} {title}", curses.A_BOLD | section_color)
                        y += 1
                        
                        if not collapsed[i]:
                            for key in keys:
                                if y >= h-1: break
                                    
                                if key == "memory" and "memory" in proc_info:
                                    mem = proc_info["memory"]
                                    for mkey, mval in mem.items():
                                        if y >= h-1: break
                                        # Key in yellow, value in green
                                        stdscr.addstr(y, 2, f"{mkey}:", curses.color_pair(3))
                                        stdscr.addstr(y, 2 + len(mkey) + 1, f" {mval}", curses.color_pair(2))
                                        y += 1
                                elif key == "cpu" and "cpu" in proc_info:
                                    cpu = proc_info["cpu"]
                                    for ckey, cval in cpu.items():
                                        if y >= h-1: break
                                        # Key in yellow, value in cyan
                                        stdscr.addstr(y, 2, f"{ckey}:", curses.color_pair(3))
                                        stdscr.addstr(y, 2 + len(ckey) + 1, f" {cval}", curses.color_pair(6))
                                        y += 1
                                elif key == "io" and "io" in proc_info and isinstance(proc_info["io"], dict):
                                    io = proc_info["io"]
                                    for iok, iov in io.items():
                                        if y >= h-1: break
                                        # Key in yellow, value in green
                                        stdscr.addstr(y, 2, f"{iok}:", curses.color_pair(3))
                                        stdscr.addstr(y, 2 + len(iok) + 1, f" {iov}", curses.color_pair(2))
                                        y += 1
                                elif key == "fd_details" and "fd_details" in proc_info:
                                    for fd, target in proc_info["fd_details"]:
                                        if y >= h-1: break
                                        target_str = str(target)
                                        if len(target_str) > w-10:
                                            target_str = target_str[:w-13] + "..."
                                        
                                        # Format file descriptors with colors
                                        stdscr.addstr(y, 2, f"fd {fd}:", curses.color_pair(6))
                                        
                                        # Use different colors based on FD type
                                        color = curses.color_pair(7)  # Default white
                                        if "socket" in target_str:
                                            color = curses.color_pair(5)  # Magenta for sockets
                                        elif "pipe" in target_str:
                                            color = curses.color_pair(3)  # Yellow for pipes
                                        elif "/dev/" in target_str:
                                            color = curses.color_pair(4)  # Blue for devices
                                        else:
                                            color = curses.color_pair(2)  # Green for files
                                            
                                        stdscr.addstr(y, 2 + len(f"fd {fd}:"), f" {target_str}", color)
                                        y += 1
                                elif key in proc_info:
                                    val = str(proc_info[key])
                                    if len(val) > w-len(key)-5:
                                        val = val[:w-len(key)-8] + "..."
                                    
                                    # Key in yellow, value based on content
                                    stdscr.addstr(y, 2, f"{key}:", curses.color_pair(3))
                                    
                                    # Choose value color based on content
                                    color = curses.color_pair(7)  # Default white
                                    val_lower = val.lower()
                                    if key == "State":
                                        if "running" in val_lower:
                                            color = curses.color_pair(2)  # Green for running
                                        elif "sleep" in val_lower:
                                            color = curses.color_pair(6)  # Cyan for sleeping
                                        elif "zombie" in val_lower or "defunct" in val_lower:
                                            color = curses.color_pair(1)  # Red for zombies
                                    elif key == "cmdline":
                                        color = curses.color_pair(2)  # Green for command line
                                    
                                    stdscr.addstr(y, 2 + len(key) + 1, f" {val}", color)
                                    y += 1
                    
                    # Only add menu options if there's space
                    if y < h-3:
                        y += 1
                        stdscr.addstr(y, 0, "Options:", curses.A_BOLD | curses.color_pair(6))
                        y += 1
                        for i, opt in enumerate(menu):
                            if y >= h-1: break
                            if mode == "menu" and i == selected_menu:
                                stdscr.addstr(y, 2, opt, curses.A_REVERSE | curses.color_pair(3))
                            else:
                                stdscr.addstr(y, 2, opt, curses.color_pair(3))
                            y += 1
                            
                    # Only add footer if there's space
                    if y < h-1:
                        # Use simpler characters to avoid UTF-8 issues
                        footer = "Up/Down:move, Left/Right:switch, Space:expand/collapse, q:return"
                        if len(footer) > w-1:
                            footer = footer[:w-1]
                        stdscr.addstr(y+1, 0, footer, curses.color_pair(7))
                    
                    stdscr.refresh()
                    
                    # Handle input
                    key = stdscr.getch()
                    if mode == "sections":
                        if key in (curses.KEY_UP, ord('k')):
                            if selected_section > 0: selected_section -= 1
                        elif key in (curses.KEY_DOWN, ord('j')):
                            if selected_section < len(sections)-1: selected_section += 1
                        elif key in (curses.KEY_RIGHT, ord('l')):
                            mode = "menu"
                        elif key in (curses.KEY_ENTER, 10, 13, ord(' ')):
                            collapsed[selected_section] = not collapsed[selected_section]
                        elif key in (ord('q'), 27):
                            return
                    elif mode == "menu":
                        if key in (curses.KEY_UP, ord('k')):
                            if selected_menu > 0: selected_menu -= 1
                        elif key in (curses.KEY_DOWN, ord('j')):
                            if selected_menu < len(menu)-1: selected_menu += 1
                        elif key in (curses.KEY_LEFT, ord('h')):
                            mode = "sections"
                        elif key in (curses.KEY_ENTER, 10, 13, ord(' ')):
                            if selected_menu == 0:
                                proc_info = get_proc_info(pid)
                            elif selected_menu == 1:
                                curses.endwin()
                                monitor_io_streams(pid)
                                stdscr.refresh()
                                curses.curs_set(0)
                            elif selected_menu == 2:
                                show_advanced_info_tui(pid)
                            elif selected_menu == 3:
                                return
                        elif key in (ord('q'), 27):
                            return
                except curses.error:
                    # Handle terminal size errors
                    stdscr.clear()
                    stdscr.refresh()
        
        # Process selector with search function
        def show_process_selector(processes):
            page_size = min(20, curses.LINES-5)
            page = 0
            selected_idx = 0
            filtered_processes = processes.copy()
            search_term = None
            
            while True:
                try:
                    stdscr.clear()
                    h, w = stdscr.getmaxyx()
                    total_pages = max(1, (len(filtered_processes) + page_size - 1) // page_size)
                    start_idx = page * page_size
                    end_idx = min(start_idx + page_size, len(filtered_processes))
                    title = f"=== Process List (Page {page+1}/{total_pages}) ==="
                    if search_term:
                        title += f" [search: {search_term}]"
                    
                    title_pos = (w - len(title)) // 2
                    if title_pos < 0: title_pos = 0
                    stdscr.addstr(0, title_pos, title, curses.A_BOLD | curses.color_pair(6))
                    
                    if not filtered_processes:
                        stdscr.addstr(2, 0, "No processes found matching criteria.", curses.color_pair(1))
                    else:
                        for idx, (pid, cmd) in enumerate(filtered_processes[start_idx:end_idx]):
                            display_cmd = cmd
                            if len(display_cmd) > w-20:
                                display_cmd = display_cmd[:w-23] + "..."
                            
                            # Format with colors
                            if idx == selected_idx:
                                attr = curses.A_REVERSE
                                stdscr.addstr(idx+2, 0, f"{start_idx+idx+1:4d}.", attr | curses.color_pair(6))
                                stdscr.addstr(idx+2, 5, f" PID: {pid:>6} ", attr | curses.color_pair(5))
                                stdscr.addstr(idx+2, 15, f"| {display_cmd}", attr | curses.color_pair(2))
                            else:
                                stdscr.addstr(idx+2, 0, f"{start_idx+idx+1:4d}.", curses.color_pair(6))
                                stdscr.addstr(idx+2, 5, f" PID: {pid:>6} ", curses.color_pair(5))
                                stdscr.addstr(idx+2, 15, f"| {display_cmd}", curses.color_pair(2))
                    
                    footer = "Up/Down:move, Left/Right:page, Enter:select, /:search, q:quit"
                    if h > page_size+3:
                        stdscr.addstr(page_size+3, 0, footer, curses.color_pair(3))
                        
                    stdscr.refresh()
                    
                    # Handle input
                    key = stdscr.getch()
                    if key in (curses.KEY_UP, ord('k')):
                        if selected_idx > 0:
                            selected_idx -= 1
                        elif page > 0:
                            page -= 1
                            selected_idx = page_size-1
                    elif key in (curses.KEY_DOWN, ord('j')):
                        max_idx = min(page_size-1, len(filtered_processes)-page*page_size-1)
                        if selected_idx < max_idx:
                            selected_idx += 1
                        elif page < (len(filtered_processes)-1)//page_size:
                            page += 1
                            selected_idx = 0
                    elif key in (curses.KEY_LEFT, ord('h')) and page > 0:
                        page -= 1
                        selected_idx = 0
                    elif key in (curses.KEY_RIGHT, ord('l')) and page < (len(filtered_processes)-1)//page_size:
                        page += 1
                        selected_idx = 0
                    elif key in (ord('/'), ord('f')):
                        search_buf = ""
                        try:
                            y_pos = min(h-1, page_size+5)
                            stdscr.addstr(y_pos, 0, "Search: " + " " * (w-8))
                            stdscr.addstr(y_pos, 0, "Search: ", curses.color_pair(3))
                            
                            curses.echo()
                            curses.curs_set(1)  # Show cursor during input
                            stdscr.move(y_pos, 8)
                            
                            # Improved input handling with proper backspace support
                            while True:
                                ch = stdscr.getch()
                                if ch in (10, 13):  # Enter - confirm search
                                    break
                                elif ch == 27:  # Escape - cancel search
                                    search_buf = ""
                                    break
                                elif ch == curses.KEY_BACKSPACE or ch in (8, 127):  # Backspace
                                    if search_buf:
                                        search_buf = search_buf[:-1]
                                        # Clear the whole input area and redraw
                                        stdscr.addstr(y_pos, 8, " " * (w-9))
                                        stdscr.addstr(y_pos, 8, search_buf, curses.color_pair(7))
                                        stdscr.move(y_pos, 8 + len(search_buf))
                                        stdscr.refresh()
                                elif 32 <= ch <= 126:  # Printable ASCII
                                    if len(search_buf) < w-10:  # Prevent overflow
                                        search_buf += chr(ch)
                                        stdscr.addstr(y_pos, 8, search_buf, curses.color_pair(7))
                                        stdscr.move(y_pos, 8 + len(search_buf))
                                        stdscr.refresh()
                        except curses.error:
                            pass
                        
                        curses.noecho()
                        curses.curs_set(0)  # Hide cursor again
                        
                        term = search_buf.strip()
                        if term:
                            search_term = term
                            filtered_processes = search_processes(processes, term)
                        else:
                            search_term = None
                            filtered_processes = processes.copy()
                        
                        page = 0
                        selected_idx = 0
                    elif key in (ord('q'), 27):
                        return None
                    elif key in (curses.KEY_ENTER, 10, 13):
                        idx = page * page_size + selected_idx
                        if filtered_processes and 0 <= idx < len(filtered_processes):
                            return filtered_processes[idx]
                except curses.error:
                    stdscr.clear()
                    stdscr.refresh()
        
        # Main menu screen
        def show_main_menu():
            selected_idx = 0
            menu_items = [
                "Processes",
                "Exit"
            ]
            
            while True:
                try:
                    stdscr.clear()
                    h, w = stdscr.getmaxyx()
                    title = "=== Process Utility (TUI mode) ==="
                    
                    # Draw title
                    title_pos = (w - len(title)) // 2
                    if title_pos < 0: title_pos = 0
                    stdscr.addstr(1, title_pos, title, curses.A_BOLD | curses.color_pair(6))
                    
                    # Draw menu items
                    for i, item in enumerate(menu_items):
                        x = (w - len(item)) // 2
                        if x < 0: x = 0
                        y = h // 2 - len(menu_items) // 2 + i
                        if y < 0 or y >= h: continue
                        
                        if i == selected_idx:
                            stdscr.addstr(y, x, item, curses.A_REVERSE | curses.color_pair(4))
                        else:
                            stdscr.addstr(y, x, item, curses.color_pair(4))
                    
                    # Draw footer
                    footer = "Use Up/Down to move, Enter to select"
                    if h > 4:
                        footer_pos = (w - len(footer)) // 2
                        if footer_pos < 0: footer_pos = 0
                        stdscr.addstr(h-2, footer_pos, footer, curses.color_pair(7))
                    
                    stdscr.refresh()
                    
                    # Handle input
                    key = stdscr.getch()
                    if key in (curses.KEY_UP, ord('k')) and selected_idx > 0:
                        selected_idx -= 1
                    elif key in (curses.KEY_DOWN, ord('j')) and selected_idx < len(menu_items) - 1:
                        selected_idx += 1
                    elif key in (curses.KEY_ENTER, 10, 13):
                        if selected_idx == 0:  # List all processes
                            processes = get_all_processes()
                            selected = show_process_selector(processes)
                            if selected:
                                pid, cmd = selected
                                show_process_details(pid, cmd)
                        elif selected_idx == 2:  # Exit
                            return "exit"
                    elif key in (ord('q'), 27):  # q or ESC
                        return "exit"
                except curses.error:
                    stdscr.clear()
                    stdscr.refresh()
        
        # Start the app with main menu
        curses.curs_set(0)  # Hide cursor
        result = show_main_menu()
        if result == "exit":
            return
    
    try:
        # Use only one wrapper for the entire application
        curses.wrapper(tui_app)
    except Exception as e:
        print(f"An error occurred: {e}")
    
    print(f"\n{YELLOW}Exiting. Goodbye!{RESET}")
    sys.exit(0)

if __name__ == "__main__":
    main()