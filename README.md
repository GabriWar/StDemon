# 🔍 StDemon - Advanced Process Monitoring Utility

StDemon is a powerful terminal-based process monitoring and inspection utility for Linux systems that provides comprehensive information about running processes with an intuitive, colorful TUI (Text User Interface).

![image](https://github.com/user-attachments/assets/cd16a185-02c7-4f5d-8f50-328e6e8f3002)
## ✨ Features

- 🔎 **Process listing and searching** - View all running processes with optional filtering
- 📊 **Detailed process information** - Memory usage, CPU utilization, file descriptors, and more
- 📡 **Stream monitoring** - Watch stdout/stderr output using strace
- 🔍 **Resource inspection** - View memory maps, open files, resource limits, and more
- 🖥️ **Interactive TUI** - Fully navigable interface with color coding for better readability
- 🌐 **Cross-platform support(kinda)** - Primary focus on Linux with basic support for Windows

## 📥 Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/StDemon.git
cd StDemon

# Make executable
chmod +x stdutil.py
# Create symlink (optional)
sudo ln -s $(pwd)/stdutil.py /usr/local/bin/StDemo
```
## 🚀 Usage

# Run directly
./stdutil.py

# Or if you created a symlink
StDemon
