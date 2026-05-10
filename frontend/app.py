from __future__ import annotations

"""
Compatibility entrypoint for Streamlit.

The real Streamlit UI currently lives in ``frontend/frontend.py``.
This file exists so existing run commands like:

    streamlit run frontend/app.py

continue to work even after the project was refactored.
"""

from frontend import main


if __name__ == "__main__":
    main()
