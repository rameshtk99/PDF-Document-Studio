"""
Configuration management for dependencies and application state
"""

import os
import sys
import subprocess
import importlib.util


class DependencyChecker:
    """Check and manage application dependencies"""
    
    def __init__(self):
        self.state = {
            'tk_available': True,
            'missing_packages': [],
            'pypdf_available': False,
            'reportlab_available': False
        }
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check for required dependencies"""
        # Check tkinter (system package)
        if importlib.util.find_spec('tkinter') is None:
            self.state['tk_available'] = False
            print("\nWarning: tkinter (GUI) not available in this environment.")
            print("You can install it on Ubuntu/Zorin with:\n    sudo apt update && sudo apt install -y python3-tk\n")
            print("Falling back to CLI mode. To use the GUI, install tkinter and restart.\n")
        
        # Check Python packages
        if importlib.util.find_spec('pypdf') is None:
            if importlib.util.find_spec('PyPDF2') is not None:
                self.state['pypdf_available'] = True
            else:
                self.state['missing_packages'].append('pypdf')
        else:
            self.state['pypdf_available'] = True
        
        if importlib.util.find_spec('reportlab') is None:
            self.state['missing_packages'].append('reportlab')
        else:
            self.state['reportlab_available'] = True
    
    def ensure_dependencies(self):
        """Ensure required packages are installed, prompt to install if missing"""
        if self.state['missing_packages']:
            print(f"\nMissing Python packages: {', '.join(self.state['missing_packages'])}")
            print("Attempting to install them with pip3 --user ...")
            try:
                subprocess.run(['pip3', 'install', '--user'] + self.state['missing_packages'], check=True)
                print("Installation attempted. Please restart the application (or re-run).")
                os._exit(0)
            except Exception as exc:
                print(f"Automatic pip install failed: {exc}")
                print(f"Please run manually:\n    pip3 install {' '.join(self.state['missing_packages'])}")
                os._exit(0)
    
    def is_gui_available(self):
        """Check if GUI mode is available"""
        return self.state['tk_available']
    
    def is_pdf_handling_available(self):
        """Check if PDF handling is available"""
        return self.state['pypdf_available']
    
    def is_reportlab_available(self):
        """Check if ReportLab is available"""
        return self.state['reportlab_available']


class AppConfig:
    """Application configuration and settings"""
    
    def __init__(self):
        self.dep_checker = DependencyChecker()
        self.gui_available = self.dep_checker.is_gui_available()
        self.pdf_available = self.dep_checker.is_pdf_handling_available()
        self.reportlab_available = self.dep_checker.is_reportlab_available()
    
    def validate_requirements(self):
        """Validate that all required dependencies are available"""
        if not self.pdf_available:
            print("Error: pypdf or PyPDF2 is required for PDF handling", file=sys.stderr)
            os._exit(1)
        
        if not self.reportlab_available:
            print("Error: reportlab is required for rendering. Install with: pip3 install reportlab", 
                  file=sys.stderr)
            os._exit(1)
