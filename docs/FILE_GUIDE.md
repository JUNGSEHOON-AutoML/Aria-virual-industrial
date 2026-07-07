# FILE_GUIDE - ARIA Swarm Codebase Directory Structure

This file provides a directory guide for all code files, image files, and primary scripts in the `/userHome/userhome4/sehoon/Agentic-CCIFPS-main` workspace, with a one-line description of their purpose.

## Root Directory

### 🐍 Python Scripts
* [agent_orchestrator.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/agent_orchestrator.py): Multi-agent swarm routing and orchestration manager in the ARIA system.
* [state_manager.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/state_manager.py): Shared state management (`AgentState`) carrying context and payload across swarm agents.
* [ralph_telegram_daemon.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/ralph_telegram_daemon.py): Live bidirectional Telegram bot daemon for system commands and image inspections.
* [mcp_client.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/mcp_client.py): Multi-protocol client for initiating and controlling Model Context Protocol (MCP) server nodes.
* [autonomous_agent.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/autonomous_agent.py): Agent logic for autonomous model execution and fallback reasoning.
* [learning_daemon.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/learning_daemon.py): Background daemon for continuously collecting training events and improving models.
* [self_improvement_loop.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/self_improvement_loop.py): Background agent loop for executing self-healing actions and micro-refactoring.
* [model_scout.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/model_scout.py): Module for discovering, testing, and downloading new vision models on demand.
* [event_bus.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/event_bus.py): Event broadcasting and subscription channel for internal swarm notifications.
* [database.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/database.py): SQLite wrapper for storing metadata of models, tasks, and system events.
* [app.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/app.py): Web dashboard application demonstrating real-time anomalous detection results and system telemetry.
* [ralph_loop.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/ralph_loop.py): Script defining the core runtime execution loops for target actions.
* [setup.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/setup.py): Packaging script for installing the patchcore library and dependencies.

### 🖼️ Root Image Files
* [test_crack.png](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/test_crack.png): Sample image containing crack defects for model validation.
* [test_normal.png](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/test_normal.png): Sample image containing no defects for model validation.
* [resized_test.png](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/resized_test.png): Temporarily resized validation image.

---

## Swarm Agent Nodes (`agents/`)

* [agents/base_agent.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/agents/base_agent.py): Abstract base class specifying shared patterns and interface methods for all agents.
* [agents/vision_agent.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/agents/vision_agent.py): Agent specialized in YOLO object detection and anomaly scoring on industrial images.
* [agents/code_agent.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/agents/code_agent.py): Agent for parsing, editing, and validating project code.
* [agents/research_agent.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/agents/research_agent.py): Agent designed for finding related research papers or models on arXiv and Hugging Face.
* [agents/industry_agent.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/agents/industry_agent.py): Agent providing domain-specific industrial manufacturing analysis and guidance.
* [agents/schedule_agent.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/agents/schedule_agent.py): Agent handling task scheduling and calendar-based integrations.
* [agents/communication_agent.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/agents/communication_agent.py): Agent managing outbound notifications, emails, and messaging channels.
* [agents/data_agent.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/agents/data_agent.py): Agent for cleaning, preprocessing, and structuring file data.
* [agents/analyst_agent.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/agents/analyst_agent.py): Agent performing statistical evaluation and data analysis.
* [agents/scout_agent.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/agents/scout_agent.py): Agent for managing model scanning and platform discovery.
* [agents/executor_agent.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/agents/executor_agent.py): Agent for running commands and executing target tasks.
* [agents/verifier_agent.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/agents/verifier_agent.py): Agent inspecting the outputs of executed tasks to assert correctness.

---

## MCP Server Nodes (`mcp_servers/`)

* [mcp_servers/filesystem_mcp.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/mcp_servers/filesystem_mcp.py): MCP server providing sandboxed file reads, writes, and list operations.
* [mcp_servers/shell_exec_mcp.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/mcp_servers/shell_exec_mcp.py): MCP server for running commands in the terminal with security limits.
* [mcp_servers/web_search_mcp.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/mcp_servers/web_search_mcp.py): MCP server for searching the web and retrieving public website contents.
* [mcp_servers/telegram_mcp.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/mcp_servers/telegram_mcp.py): MCP server wrapping Telegram API for sending alerts and messages.
* [mcp_servers/huggingface_mcp.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/mcp_servers/huggingface_mcp.py): MCP server to search and interact with Hugging Face Hub.
* [mcp_servers/kaggle_mcp.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/mcp_servers/kaggle_mcp.py): MCP server to download datasets and check Kaggle status.
* [mcp_servers/arxiv_mcp.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/mcp_servers/arxiv_mcp.py): MCP server for searching academic papers on arXiv.
* [mcp_servers/weather_mcp.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/mcp_servers/weather_mcp.py): MCP server for querying regional weather forecasts.
* [mcp_servers/youtube_mcp.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/mcp_servers/youtube_mcp.py): MCP server for searching video contents on YouTube.

---

## Core Anomaly detection Model (`src/patchcore/`)

* [src/patchcore/__init__.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/src/patchcore/__init__.py): Package initialization for the Patchcore anomaly detection algorithm.
* [src/patchcore/patchcore.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/src/patchcore/patchcore.py): Implementation of the core Patchcore anomaly detection model architecture.
* [src/patchcore/common.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/src/patchcore/common.py): Core utilities and helper layers shared across patchcore submodules.
* [src/patchcore/backbones.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/src/patchcore/backbones.py): Definition of deep learning CNN backbones used for feature extraction.
* [src/patchcore/sampler.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/src/patchcore/sampler.py): Implementation of coreset sampling techniques to reduce memory footprints.
* [src/patchcore/metrics.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/src/patchcore/metrics.py): Metrics definitions (e.g. AUROC) for evaluating anomaly detection models.
* [src/patchcore/logging_utils.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/src/patchcore/logging_utils.py): Logging patterns and metrics writing helpers for model training.
* [src/patchcore/utils.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/src/patchcore/utils.py): Math and array manipulation utilities for patchcore inference.
* [src/patchcore/datasets/mvtec.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/src/patchcore/datasets/mvtec.py): PyTorch dataset class for MVTec anomaly detection benchmark.
* [src/patchcore/datasets/visa.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/src/patchcore/datasets/visa.py): PyTorch dataset class for VisA industrial anomaly dataset.
* [src/patchcore/datasets/__init__.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/src/patchcore/datasets/__init__.py): Dataset loading and registry helper functions.

---

## Web Frontend Assets

* [templates/index.html](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/templates/index.html): Main HTML template for the web dashboard interface.
* [static/css/style.css](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/static/css/style.css): Cyberpunk-inspired layout and styling sheet for the dashboard front-end.
* [static/js/main.js](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/static/js/main.js): Main Javascript logic driving telemetry, alerts, and live image refreshes.

---

## Task Skills (`skills/`)

* [skills/ccifps_vision/local_agent.py](file:///userHome/userhome4/sehoon/Agentic-CCIFPS-main/skills/ccifps_vision/local_agent.py): Local execution logic for model assessment and visual anomaly mapping.
