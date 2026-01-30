package plugin

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// Logger logs interactions with plugins.
type Logger struct {
	logPath string
	mu      sync.RWMutex
}

// InteractionLog represents a single logged interaction.
type InteractionLog struct {
	Timestamp  string `json:"timestamp"`
	PluginID   string `json:"pluginId"`
	Type       string `json:"type"` // "input", "output", "error", "handshake"
	Content    string `json:"content"`
	Success    bool   `json:"success"`
	DurationMs int64  `json:"durationMs,omitempty"`
}

// NewLogger creates a new plugin logger.
func NewLogger(dataDir string) (*Logger, error) {
	logPath := filepath.Join(dataDir, "plugin_logs.txt")
	return &Logger{logPath: logPath}, nil
}

// LogInteraction logs an interaction with a plugin.
func (l *Logger) LogInteraction(pluginID, typeStr, content string, success bool, durationMs int64) error {
	l.mu.Lock()
	defer l.mu.Unlock()

	// Simple text format: timestamp | plugin_id | type | success | duration_ms | content
	// Replacing newlines in content to keep one log per line
	sanitizedContent := strings.ReplaceAll(content, "\n", "\\n")

	line := fmt.Sprintf("%s|%s|%s|%v|%d|%s\n",
		time.Now().Format(time.RFC3339),
		pluginID,
		typeStr,
		success,
		durationMs,
		sanitizedContent,
	)

	f, err := os.OpenFile(l.logPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return fmt.Errorf("opening log file: %w", err)
	}
	defer f.Close()

	if _, err := f.WriteString(line); err != nil {
		return fmt.Errorf("writing log: %w", err)
	}

	return nil
}

// GetLogs returns the last N logs.
func (l *Logger) GetLogs(limit int) ([]InteractionLog, error) {
	l.mu.RLock()
	defer l.mu.RUnlock()

	if limit <= 0 {
		limit = 100
	}

	f, err := os.Open(l.logPath)
	if err != nil {
		if os.IsNotExist(err) {
			return []InteractionLog{}, nil
		}
		return nil, fmt.Errorf("opening log file: %w", err)
	}
	defer f.Close()

	var lines []string
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		lines = append(lines, scanner.Text())
	}

	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("reading logs: %w", err)
	}

	// Get last N lines
	start := 0
	if len(lines) > limit {
		start = len(lines) - limit
	}

	logs := make([]InteractionLog, 0, len(lines)-start)
	for i := start; i < len(lines); i++ {
		parts := strings.SplitN(lines[i], "|", 6)
		if len(parts) < 6 {
			continue
		}

		var duration int64
		fmt.Sscanf(parts[4], "%d", &duration)

		success := parts[3] == "true"

		logs = append(logs, InteractionLog{
			Timestamp:  parts[0],
			PluginID:   parts[1],
			Type:       parts[2],
			Success:    success,
			DurationMs: duration,
			Content:    strings.ReplaceAll(parts[5], "\\n", "\n"),
		})
	}

	// Reverse to show newest first
	for i, j := 0, len(logs)-1; i < j; i, j = i+1, j-1 {
		logs[i], logs[j] = logs[j], logs[i]
	}

	return logs, nil
}
