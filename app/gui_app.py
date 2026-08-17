"""
Application entry point and coordination
"""

import os
import sys
import json
import tempfile
import threading
from typing import Optional

# GUI imports will be loaded conditionally
tk = None
filedialog = None
messagebox = None
ttk = None
tkFont = None


def init_gui():
    """Initialize GUI modules"""
    global tk, filedialog, messagebox, ttk, tkFont
    
    if tk is not None:
        return True  # Already initialized
    
    try:
        import tkinter as tk_module
        from tkinter import filedialog as filedialog_module
        from tkinter import messagebox as messagebox_module
        from tkinter import ttk as ttk_module
        import tkinter.font as tkFont_module
        
        tk = tk_module
        filedialog = filedialog_module
        messagebox = messagebox_module
        ttk = ttk_module
        tkFont = tkFont_module
        
        return True
    except ImportError:
        return False


class FooterApp:
    """Main GUI application for PDF Footer Editor (preserves existing functionality)"""
    
    def __init__(self, root):
        if not init_gui():
            raise RuntimeError("Tkinter is not available")
        
        self.root = root
        root.title("PDF Document Studio - Simple Footer Tool (Classic)")
        root.geometry("800x600")

        from utils.constants import PROJECT_ROOT
        icon_path = os.path.join(PROJECT_ROOT, 'logo.ico')
        if os.path.exists(icon_path):
            try:
                root.iconbitmap(icon_path)
            except tk.TclError:
                pass

        # Get draft file path in user's temp directory
        self.draft_file_path = os.path.join(tempfile.gettempdir(), "pdf_footer_draft.json")
        
        # Get available system fonts for Tkinter
        self.available_fonts = list(tkFont.families())
        
        # Use specified common fonts that are available
        common_fonts = ['Arial', 'Times New Roman', 'Courier New', 'Verdana', 
                       'Tahoma', 'Georgia', 'Preeti', 'Calibri', 'Ganesh', 'Kantipur']
        
        # Filter to only include fonts that are actually available
        self.fonts_available = [font for font in common_fonts if font in self.available_fonts]
        if not self.fonts_available:
            self.fonts_available = self.available_fonts[:10]  # Fallback to first 10 available fonts
        
        # Default font - use first available font
        self.font_var = tk.StringVar(value=self.fonts_available[0])
        self.font_size_var = tk.IntVar(value=16)
        self.col_count_var = tk.IntVar(value=5)
        
        # Initialize GUI
        self._init_ui()
        
        # Auto-load draft
        self.load_draft(auto=True)
    
    def _init_ui(self):
        """Initialize user interface"""
        # File selection
        tk.Label(self.root, text="Source PDF:").pack(pady=2)
        self.src_var = tk.StringVar()
        tk.Entry(self.root, textvariable=self.src_var, width=80).pack()
        tk.Button(self.root, text="Browse", command=self.browse_src).pack(pady=2)
        
        # Font name & size
        frame_font = tk.Frame(self.root)
        frame_font.pack(pady=5)
        tk.Label(frame_font, text="Font Name:").grid(row=0, column=0)
        font_dropdown = ttk.Combobox(frame_font, textvariable=self.font_var,
                                     values=self.fonts_available, state="readonly", width=30)
        font_dropdown.grid(row=0, column=1)
        tk.Label(frame_font, text="Font Size:").grid(row=0, column=2, padx=(10,0))
        tk.Entry(frame_font, textvariable=self.font_size_var, width=5).grid(row=0, column=3)
        
        # Footer columns
        frame_col = tk.Frame(self.root)
        frame_col.pack(pady=5)
        tk.Label(frame_col, text="Number of Footer Columns:").grid(row=0, column=0)
        tk.Entry(frame_col, textvariable=self.col_count_var, width=5).grid(row=0, column=1)
        tk.Button(frame_col, text="Set Columns", command=self.set_columns).grid(row=0, column=2, padx=5)
        
        # Footer entry fields placeholder
        self.entries_frame = None
        self.footer_entries = []
        
        # Run button
        self.run_button = tk.Button(self.root, text="Add Footer", command=self.run, bg="green", fg="white")
        self.run_button.pack(pady=15)
    
    def browse_src(self):
        """Browse for source PDF"""
        file = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if file:
            self.src_var.set(file)
    
    def set_columns(self):
        """Set number of footer columns"""
        self.footer_entries = []
        col_count = self.col_count_var.get()
        if hasattr(self, 'entries_frame') and self.entries_frame:
            self.entries_frame.destroy()
        
        self.entries_frame = tk.Frame(self.root)
        self.entries_frame.pack(pady=10)
        
        # Get the selected font, fallback to Arial if not available
        selected_font = self.font_var.get()
        if selected_font not in self.available_fonts:
            selected_font = 'Arial'
        
        font_obj = tkFont.Font(family=selected_font, size=self.font_size_var.get())
        
        for i in range(col_count):
            tk.Label(self.entries_frame, text=f"Column {i+1} Line 1:").grid(row=i, column=0, sticky="e")
            line1_var = tk.StringVar()
            entry1 = tk.Entry(self.entries_frame, textvariable=line1_var, width=25, font=font_obj)
            entry1.grid(row=i, column=1)
            
            tk.Label(self.entries_frame, text=f"Column {i+1} Line 2:").grid(row=i, column=2, sticky="e")
            line2_var = tk.StringVar()
            entry2 = tk.Entry(self.entries_frame, textvariable=line2_var, width=25, font=font_obj)
            entry2.grid(row=i, column=3)
            
            self.footer_entries.append((line1_var, line2_var))
    
    def save_draft(self):
        """Save current footer configuration as draft"""
        data = {
            "src": self.src_var.get(),
            "columns": self.col_count_var.get(),
            "font_name": self.font_var.get(),
            "font_size": self.font_size_var.get(),
            "footers": [(l1.get(), l2.get()) for l1, l2 in self.footer_entries]
        }
        try:
            with open(self.draft_file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            # Don't show error for draft saving - it's not critical
            print(f"Could not save draft: {e}")
    
    def load_draft(self, auto=False):
        """Load footer configuration from draft"""
        try:
            if not os.path.exists(self.draft_file_path):
                return
            with open(self.draft_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.src_var.set(data.get("src",""))
            self.col_count_var.set(data.get("columns",5))
            
            # Load font name with fallback
            saved_font = data.get("font_name", self.fonts_available[0])
            if saved_font in self.available_fonts:
                self.font_var.set(saved_font)
            else:
                self.font_var.set(self.fonts_available[0])
            
            self.font_size_var.set(data.get("font_size",16))
            self.set_columns()
            for (l1_var,l2_var),(val1,val2) in zip(self.footer_entries,data.get("footers",[])):
                l1_var.set(val1)
                l2_var.set(val2)
            if not auto:
                messagebox.showinfo("Draft Loaded","Footer draft loaded successfully!")
        except Exception as e:
            # Don't show error for draft loading - it's not critical
            if not auto:
                print(f"Could not load draft: {e}")
    
    def set_ui_state(self, enabled):
        """Enable or disable UI elements during processing"""
        state = "normal" if enabled else "disabled"
        self.run_button.config(state=state)
    
    def process_footer(self, src, dest):
        """Process the footer in a separate thread (PDF only)"""
        try:
            from pdf import FooterGenerator
            
            footer_items = [(l1.get(), l2.get()) for l1, l2 in self.footer_entries]
            
            # Only PDF input is supported
            if not src.lower().endswith(".pdf"):
                self.root.after(0, lambda: messagebox.showerror(
                    "Error",
                    "Only PDF input is supported. Convert Excel files to PDF separately and try again."
                ))
                return
            
            input_pdf = src
            
            FooterGenerator.add_footer_to_pdf(input_pdf, dest, footer_items,
                              font_name=self.font_var.get(),
                              font_size=self.font_size_var.get())
            
            if os.path.exists(dest):
                try:
                    self.save_draft()
                except:
                    pass
            
            # Show success message in main thread
            self.root.after(0, lambda: messagebox.showinfo("Success", f"Footer added successfully!\nOutput: {dest}"))
            
        except Exception as e:
            # Capture now -- `e` is unbound by the time a deferred lambda
            # would run on the main thread via after().
            error_message = str(e)
            self.root.after(0, lambda: messagebox.showerror("Error", error_message))
        finally:
            # Re-enable UI in main thread
            self.root.after(0, lambda: self.set_ui_state(True))
            self.root.after(0, lambda: self.run_button.config(text="Add Footer", bg="green"))
    
    def run(self):
        """Execute footer addition"""
        src = self.src_var.get()
        if not src:
            messagebox.showerror("Error", "Please select source file")
            return
        if not self.footer_entries:
            messagebox.showerror("Error", "Please set number of columns and fill footer values")
            return
        
        # Generate suggested file name
        base_name, ext = os.path.splitext(os.path.basename(src))
        suggested_name = f"{base_name}_footer.pdf"
        initial_dir = os.path.dirname(src) if src else ""
        
        # Ask user for destination with suggested file name
        dest = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=suggested_name,
            initialdir=initial_dir,
            filetypes=[("PDF files", "*.pdf")],
            title="Save Output PDF As"
        )
        
        if not dest:  # User cancelled
            return
        
        # Change button to "Wait..." and disable UI
        self.run_button.config(text="Wait...", bg="gray", state="disabled")
        self.set_ui_state(False)
        
        # Process in a separate thread to keep UI responsive
        thread = threading.Thread(target=self.process_footer, args=(src, dest))
        thread.daemon = True
        thread.start()
