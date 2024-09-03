on runTerminalCommand(commandString)

tell application "Terminal"
    do script commandString
end tell

end runTerminalCommand