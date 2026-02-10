# main.py
import asyncio
import sys
import pandas as pd
import customtkinter as ctk
from tkinter import filedialog, messagebox
from copilot import CopilotClient
from tools import send_email
import json
import time  # only used for small UI breathing room if needed

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class ReferralAgentApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Construction Referral Email Agent")
        self.geometry("1100x800")
        self.client = None
        self.session = None
        self.customers_df = None
        self.specials_df = None

        self.create_widgets()

    def create_widgets(self):
        # Title
        ctk.CTkLabel(self, text="Construction Referral Email Agent", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=20)

        # File selection frame
        file_frame = ctk.CTkFrame(self)
        file_frame.pack(pady=10, padx=20, fill="x")

        ctk.CTkButton(file_frame, text="Select Customers CSV", command=self.load_customers).pack(side="left", padx=10, pady=10)
        ctk.CTkButton(file_frame, text="Select Specials CSV", command=self.load_specials).pack(side="left", padx=10, pady=10)

        # Previews
        self.customer_label = ctk.CTkLabel(self, text="Customers loaded: 0")
        self.customer_label.pack(pady=5)

        self.preview_text = ctk.CTkTextbox(self, height=150)
        self.preview_text.pack(pady=10, padx=20, fill="x")

        # Instructions
        ctk.CTkLabel(self, text="Additional Instructions (optional):").pack(anchor="w", padx=20)
        self.instructions = ctk.CTkTextbox(self, height=80)
        self.instructions.pack(pady=5, padx=20, fill="x")

        # Controls
        control_frame = ctk.CTkFrame(self)
        control_frame.pack(pady=15, fill="x", padx=20)

        self.dry_run = ctk.CTkCheckBox(control_frame, text="Dry Run (Preview only - no sending)")
        self.dry_run.pack(side="left", padx=20)

        self.run_button = ctk.CTkButton(control_frame, text="Generate & Send Emails", fg_color="green",
                                        command=self.start_campaign, height=40, font=ctk.CTkFont(size=16))
        self.run_button.pack(side="right", padx=20)

        # Progress & Log
        self.progress = ctk.CTkProgressBar(self)
        self.progress.pack(pady=10, padx=20, fill="x")
        self.progress.set(0)

        self.log_text = ctk.CTkTextbox(self, height=300)
        self.log_text.pack(pady=10, padx=20, fill="both", expand=True)

    def log(self, message):
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.update_idletasks()  # Helps keep UI responsive during long runs

    def load_customers(self):
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if path:
            try:
                self.customers_df = pd.read_csv(path)
                self.customer_label.configure(text=f"Customers loaded: {len(self.customers_df)}")
                self.preview_text.delete("1.0", "end")
                self.preview_text.insert("end", self.customers_df.head(10).to_string(index=False))
                self.log(f"Customers file loaded: {len(self.customers_df)} records")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load customers CSV:\n{e}")

    def load_specials(self):
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if path:
            try:
                self.specials_df = pd.read_csv(path)
                self.log(f"Specials loaded: {len(self.specials_df)} areas of interest")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load specials CSV:\n{e}")

    def start_campaign(self):
        if self.customers_df is None or self.specials_df is None:
            messagebox.showerror("Missing files", "Please load both Customers and Specials CSV files first.")
            return

        self.run_button.configure(state="disabled")
        self.log("Starting referral email campaign... (this may take a while)")

        # Run the async agent – blocks UI thread (acceptable for now)
        try:
            asyncio.run(self.run_agent())
        except Exception as e:
            self.log(f"ERROR during campaign: {str(e)}")
            messagebox.showerror("Campaign Error", str(e))
        finally:
            self.run_button.configure(state="normal")
            self.log("Campaign process finished.")

    async def run_agent(self):
        try:
            if self.client is None:
                self.log("Initializing Copilot client...")
                self.client = CopilotClient()
                await self.client.start()

            self.log("Creating agent session...")
            self.session = await self.client.create_session({
                "model": "gpt-4.1",          # Change to "gpt-4o" / "gpt-5" if your plan supports it
                "streaming": True,
                "tools": [send_email],
            })

            def handle_event(event):
                try:
                    event_type = event.type
                    if hasattr(event_type, 'value'):
                        event_type = event_type.value  # unwrap if it's an enum
                    event_type = str(event_type).lower()  # normalize
                except AttributeError:
                    self.log("Event missing .type — skipping")
                    return

                data = event.data

                # Skip internal/noisy events
                if event_type in ["pending_messages.modified", "session.usage_info", "session.compaction", "session.start"]:
                    return

                # Streaming deltas (common names from SDK examples)
                if "delta" in event_type or event_type == "assistant.message_delta":
                    # Try common attribute names
                    chunk = getattr(data, 'content', None) or getattr(data, 'delta_content', None) or getattr(data, 'deltaContent', None) or ''
                    if isinstance(chunk, str) and chunk.strip():
                        self.log(f"Stream chunk: {chunk}")
                    return

                # Full assistant message
                if event_type == "assistant.message":
                    content = getattr(data, 'content', '')
                    if content.strip():
                        self.log(f"Full assistant message:\n{content}")
                    return

                # Session idle → good signal that agent is done
                if event_type == "session.idle":
                    self.log("Session idle — agent processing complete")
                    return

                # Tool start
                if "tool" in event_type and ("start" in event_type or "executionstart" in event_type):
                    tool_name = getattr(data, 'tool_name', 'unknown')
                    self.log(f"→ Tool started: {tool_name}")
                    return

                # Tool end / complete
                if "tool" in event_type and ("end" in event_type or "complete" in event_type or "executioncomplete" in event_type):
                    result = getattr(data, 'result', None)
                    if result:
                        status = getattr(result, 'status', 'unknown')
                        to_email = getattr(result, 'to', getattr(result, 'to_email', 'unknown'))
                        error = getattr(result, 'error', None)
                        if error:
                            self.log(f"→ Tool ERROR for {to_email}: {error}")
                        else:
                            self.log(f"→ Tool SUCCESS → {status} to {to_email}")
                    return

                # Errors
                if "error" in event_type:
                    msg = getattr(data, 'message', str(data))
                    self.log(f"Agent error: {msg}")
                    return

                # Fallback for unknown events — safe check without .values()
                try:
                    data_dict = vars(data) if hasattr(data, '__dict__') else {}
                    if data_dict:  # only log if there's something
                        self.log(f"Unhandled event: {event_type} — data attrs: {list(data_dict.keys())}")
                except Exception:
                    self.log(f"Unhandled event: {event_type} — (could not inspect data)")

            self.session.on(handle_event)

            customers_json = self.customers_df.to_json(orient="records", indent=2)
            specials_json = self.specials_df.to_json(orient="records", indent=2)

            extra = self.instructions.get("1.0", "end").strip()
            is_dry = self.dry_run.get()
            dry_run_note = (
                "IMPORTANT DRY-RUN MODE: Do NOT call send_email. "
                "Instead, output each full email (subject + body) clearly in your final response."
                if is_dry else ""
            )

            prompt = f"""You are an expert, warm, professional email copywriter for a trusted local construction company.

Current customers (name, email, area_of_interest):
{customers_json}

This month's specials & referral rewards (match by area_of_interest):
{specials_json}

Extra user instructions: {extra or "None"}

{dry_run_note}

Instructions:
- For each customer, create ONE personalized referral email
- Naturally mention their past area of interest
- Highlight the matching monthly special
- Gently encourage referring friends/family with the reward
- Friendly tone, clear call-to-action (reply / call / visit website)
- Always include a CAN-SPAM footer with company physical address and unsubscribe instructions

If NOT dry-run: use the send_email tool for each customer.
If dry-run: do NOT use the tool — print each email clearly instead.

Process all customers in this single interaction."""

            self.log("Sending prompt to agent...")
            await self.session.send_and_wait({"prompt": prompt})

            self.log("Prompt sent. Waiting for streaming/tool events... (watch for 'Stream chunk', 'Full assistant message', or tool logs)")
            await asyncio.sleep(10)  # give time for final idle/tool events to arrive
            self.log("Agent run concluded — check log for generated emails or errors.")

        except Exception as e:
            self.log(f"Agent runtime error: {str(e)}")
            import traceback
            self.log(traceback.format_exc())
            raise

        finally:
            if self.session:
                await self.session.destroy()
                self.session = None
                self.log("Session cleaned up.")


if __name__ == "__main__":
    app = ReferralAgentApp()
    app.mainloop()