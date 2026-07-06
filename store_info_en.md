# Droid Dev Helper Store Information

## Overview
Droid Dev Helper is a smart device control companion application for Android developers and users who need convenient device control. By fully integrating ADB and Scrcpy, it allows you to perform device mirroring, status checks, system shortcut key transmissions, and logcat analysis consistently across Windows, Linux, and macOS without complex configurations.

## Description
This application is a graphical utility designed to help you manage Android development and testing at a glance without having to deal with complex command-line interfaces. It automatically detects and displays the manufacturer, model, OS version, and screen resolution in real time upon connection. Equipped with a background thread detection mechanism, it ensures a smooth and fluid experience on Windows without UI freezing. You can control your smartphone on a large screen using the mirroring feature, and intuitively debug application errors through real-time logcat streaming. In addition, you can visualize smartphone layout bounds, expose touch feedback, or enter developer settings with a single click, dramatically reducing testing and quality assurance lead times.

## Features
- Real-time Mirroring and Remote Control
  Instantly open a high-resolution mirroring window upon device connection to control it via mouse and keyboard.
- Background Automatic Device Detection
  Monitors device connection status and system properties in real time using a thread-pool mechanism without blocking the system UI.
- One-Click Developer Tool Shortcuts
  Supports quick toggling of layout bounds, touch feedback rendering, and direct navigation to the developer options screen.
- Hardware and Shortcut Key Transmissions
  Allows you to control the device's Power button, Home button, Back button, and App switcher button directly from the application GUI.
- Text Input and Package Data Clearing
  Send English or Korean text strings to the device in batch mode or easily wipe app data of a specific package name.
- Real-time Logcat Streaming and Screen Capture
  Stream real-time debug logs into a scrollable log viewer and easily capture screenshot images saved directly to your desktop.
