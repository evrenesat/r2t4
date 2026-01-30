package plugin

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"

	r2t4v1 "github.com/evren/r2t4/server/gen/r2t4/v1"
)

// Manager handles the lifecycle of plugins.
type Manager struct {
	dataDir  string
	regPath  string
	registry map[string]*r2t4v1.Plugin
	mu       sync.RWMutex
	executor *Executor
	logger   *Logger
}

// NewManager creates a new plugin manager.
func NewManager(dataDir string, logger *Logger) (*Manager, error) {
	regPath := filepath.Join(dataDir, "plugins.json")

	m := &Manager{
		dataDir:  dataDir,
		regPath:  regPath,
		registry: make(map[string]*r2t4v1.Plugin),
		logger:   logger,
	}

	m.executor = NewExecutor(dataDir, logger)

	if err := m.loadRegistry(); err != nil {
		// Log error but continue with empty registry if file doesn't exist
		if !os.IsNotExist(err) {
			return nil, fmt.Errorf("loading plugin registry: %w", err)
		}
	}

	return m, nil
}

// RegisterPlugin validates and registers a new plugin.
func (m *Manager) RegisterPlugin(path string) (*r2t4v1.Plugin, error) {
	// 1. Verify file exists and is executable
	absPath, err := filepath.Abs(path)
	if err != nil {
		return nil, fmt.Errorf("invalid path: %w", err)
	}

	info, err := os.Stat(absPath)
	if err != nil {
		return nil, fmt.Errorf("plugin file not found: %w", err)
	}
	if info.Mode()&0111 == 0 {
		return nil, fmt.Errorf("plugin file is not executable")
	}

	// 2. Run handshake
	resp, latency, err := m.executor.Handshake(absPath)
	if err != nil {
		return nil, fmt.Errorf("handshake failed: %w", err)
	}

	// 3. Create plugin entry
	// Generate ID from name to avoid duplicates
	id := resp.Name // Simple ID for now

	plugin := &r2t4v1.Plugin{
		Id:           id,
		Name:         resp.Name,
		Version:      resp.Version,
		Path:         absPath,
		Status:       r2t4v1.PluginStatus_PLUGIN_STATUS_ACTIVE,
		Capabilities: resp.Capabilities,
		Description:  resp.Description,
	}

	// Map type string to enum
	switch resp.PluginType {
	case "subtitle_provider":
		plugin.Type = r2t4v1.PluginType_PLUGIN_TYPE_SUBTITLE_PROVIDER
	case "web_search":
		plugin.Type = r2t4v1.PluginType_PLUGIN_TYPE_WEB_SEARCH
	case "imdb_score":
		plugin.Type = r2t4v1.PluginType_PLUGIN_TYPE_IMDB_SCORE
	default:
		plugin.Type = r2t4v1.PluginType_PLUGIN_TYPE_UNSPECIFIED
	}

	m.mu.Lock()
	m.registry[id] = plugin
	m.saveRegistry()
	m.mu.Unlock()

	// Log success
	m.logger.LogInteraction(id, "register", fmt.Sprintf("Registered plugin %s (latency: %dms)", plugin.Name, latency), true, latency)

	return plugin, nil
}

// UnregisterPlugin removes a plugin.
func (m *Manager) UnregisterPlugin(id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if _, exists := m.registry[id]; !exists {
		return fmt.Errorf("plugin not found")
	}

	delete(m.registry, id)
	return m.saveRegistry()
}

// GetPlugin returns a plugin by ID.
func (m *Manager) GetPlugin(id string) (*r2t4v1.Plugin, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	p, exists := m.registry[id]
	if !exists {
		return nil, fmt.Errorf("plugin not found")
	}
	return p, nil
}

// ListPlugins returns all registered plugins.
func (m *Manager) ListPlugins() []*r2t4v1.Plugin {
	m.mu.RLock()
	defer m.mu.RUnlock()

	plugins := make([]*r2t4v1.Plugin, 0, len(m.registry))
	for _, p := range m.registry {
		plugins = append(plugins, p)
	}
	return plugins
}

// SetPluginStatus enables or disables a plugin.
func (m *Manager) SetPluginStatus(id string, enabled bool) (*r2t4v1.Plugin, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	p, exists := m.registry[id]
	if !exists {
		return nil, fmt.Errorf("plugin not found")
	}

	if enabled {
		p.Status = r2t4v1.PluginStatus_PLUGIN_STATUS_ACTIVE
	} else {
		p.Status = r2t4v1.PluginStatus_PLUGIN_STATUS_DISABLED
	}

	m.saveRegistry()
	return p, nil
}

// TestPlugin processes a handshake to verify the plugin is working.
func (m *Manager) TestPlugin(id string) (bool, string, int64, error) {
	m.mu.RLock()
	p, exists := m.registry[id]
	m.mu.RUnlock()

	if !exists {
		return false, "Plugin not found", 0, fmt.Errorf("plugin not found")
	}

	_, latency, err := m.executor.Handshake(p.Path)
	if err != nil {
		m.logger.LogInteraction(id, "test", fmt.Sprintf("Test failed: %v", err), false, latency)
		return false, err.Error(), latency, nil
	}

	m.logger.LogInteraction(id, "test", fmt.Sprintf("Test passed (latency: %dms)", latency), true, latency)
	return true, "Handshake successful", latency, nil
}

// ExecutePlugin runs a plugin with specific params (used for testing mostly).
func (m *Manager) Execute(id, action string, params any) (any, error) {
	m.mu.RLock()
	p, exists := m.registry[id]
	m.mu.RUnlock()

	if !exists {
		return nil, fmt.Errorf("plugin not found")
	}

	if p.Status != r2t4v1.PluginStatus_PLUGIN_STATUS_ACTIVE {
		return nil, fmt.Errorf("plugin is disabled")
	}

	req := PluginRequest{
		RequestID: "exec_" + generateID(),
		Action:    action,
		Params:    params,
	}

	resp, latency, err := m.executor.Execute(p.Path, req)
	if err != nil {
		m.logger.LogInteraction(id, "execute", fmt.Sprintf("Error: %v", err), false, latency)
		return nil, err
	}

	if !resp.Success {
		m.logger.LogInteraction(id, "execute", fmt.Sprintf("Plugin reported error: %v", resp.Error), false, latency)
		return nil, fmt.Errorf("plugin error: %v", resp.Error)
	}

	m.logger.LogInteraction(id, "execute", fmt.Sprintf("Success: %s", action), true, latency)
	return resp.Result, nil
}

func (m *Manager) loadRegistry() error {
	m.mu.Lock()
	defer m.mu.Unlock()

	data, err := os.ReadFile(m.regPath)
	if err != nil {
		return err
	}

	return json.Unmarshal(data, &m.registry)
}

func (m *Manager) saveRegistry() error {
	data, err := json.MarshalIndent(m.registry, "", "  ")
	if err != nil {
		return err
	}

	return os.WriteFile(m.regPath, data, 0644)
}

func generateID() string {
	// Simple unique ID generation
	return fmt.Sprintf("%d", os.Getpid()) // Placeholder
}
