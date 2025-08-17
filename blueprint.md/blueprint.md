Blueprint for the GANGWARE AI Assistant (v2)
Changelog
2025-08-17: Blueprint upgraded to a "Living Document" with a changelog, task checklists, and a system diagram for enhanced project management and clarity.

2025-08-17: Initial blueprint creation.

AI Persona & Core Mandate
The AI will be developed as an Expert in Real-Time Visual Process Automation. Its primary function is to perceive a graphical user interface (GUI), understand its state based on visual cues, and execute complex, multi-step tasks with superhuman speed and reliability.

Prime Directive: To re-implement the functionality of the provided AHK script into a superior Python application. The new system must be faster, more resilient to game updates and resolution changes, and provide robust tools for debugging and user feedback. It will operate under a strict non-invasive protocol.

System Architecture Diagram
Code snippet

graph TD;
    subgraph User Interaction
        A[User Presses Hotkey] --> B{HotkeyManager};
    end
    subgraph AI Core
        B --> C[Task Queue];
        C --> D{Worker Thread};
    end
    subgraph AI Actions
        D -- Reads Task --> E[Macros];
        E -- Uses --> F[VisionController];
        E -- Uses --> G[InputController];
    end
    subgraph Feedback Loop
        G -- Interacts with --> H[Game Window];
        F -- Perceives --> H;
        D -- Updates --> I[GUI Overlay];
    end
Phase 1: Foundation - The Sensory and Motor Cortex
Objective: To build the AI's core abilities to see and interact with the game world.

[ ] Module: Vision System (vision.py)

[ ] Create VisionController class.

[ ] Implement find_template method using OpenCV.

[ ] Add error handling for when templates are not found.

[ ] Module: Control System (controls.py)

[ ] Create InputController class.

[ ] Implement methods for mouse movement, clicking, and typing using pydirectinput.

[ ] Module: Configuration Core (config.py)

[ ] Create ConfigManager class.

[ ] Implement methods to load, get, and save settings from config.ini.

Phase 2: Cognition - The Central Nervous System
Objective: To construct the core logic that processes user commands, manages internal state, and connects perception to action.

[ ] Module: State & Task Management

[ ] Implement the thread-safe StateManager class in state.py.

[ ] Implement the HotkeyManager thread in hotkey_manager.py to listen for commands and populate the task queue.

[ ] Implement the Worker thread in worker.py to process tasks from the queue.

Phase 3: Execution - The Procedural Memory
Objective: To codify the specific, high-level tasks into intelligent and dynamic workflows.

[ ] Module: Macro Library (macros/)

[ ] Create the armor_swapper.py module.

[ ] Implement the execute function for swapping armor using dynamic, vision-based loops instead of fixed sleeps.

[ ] Create combat.py for other macros (Tek Punch, etc.).

Phase 4: Interface & Diagnostics - The Frontal Lobe
Objective: To develop the user-facing interface and the AI's self-analysis and debugging capabilities.

[ ] Module: User Interface (gui/overlay.py)

[ ] Create the OverlayWindow class using PyQt6.

[ ] Design the UI to be frameless, on-top, and themed.

[ ] Implement a signal/slot system for safe, cross-thread UI updates.

[ ] Module: Self-Analysis & Logging

[ ] Configure the global logging setup in main.py.

[ ] Integrate logging calls (INFO, DEBUG, ERROR) throughout all modules.

[ ] Implement a "dry run" mode flag in the ConfigManager and Worker.
