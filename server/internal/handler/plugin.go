package handler

import (
	"context"

	"connectrpc.com/connect"
	r2t4v1 "github.com/evren/r2t4/server/gen/r2t4/v1"
	"github.com/evren/r2t4/server/gen/r2t4/v1/r2t4v1connect"
	"github.com/evren/r2t4/server/internal/plugin"
)

// PluginHandler implements the PluginService.
type PluginHandler struct {
	r2t4v1connect.UnimplementedPluginServiceHandler
	manager *plugin.Manager
}

// NewPluginHandler creates a new PluginHandler.
func NewPluginHandler(m *plugin.Manager) *PluginHandler {
	return &PluginHandler{manager: m}
}

// ListPlugins returns all registered plugins.
func (h *PluginHandler) ListPlugins(
	ctx context.Context,
	req *connect.Request[r2t4v1.ListPluginsRequest],
) (*connect.Response[r2t4v1.ListPluginsResponse], error) {
	plugins := h.manager.ListPlugins()
	return connect.NewResponse(&r2t4v1.ListPluginsResponse{
		Plugins: plugins,
	}), nil
}

// RegisterPlugin registers a new plugin.
func (h *PluginHandler) RegisterPlugin(
	ctx context.Context,
	req *connect.Request[r2t4v1.RegisterPluginRequest],
) (*connect.Response[r2t4v1.RegisterPluginResponse], error) {
	plugin, err := h.manager.RegisterPlugin(req.Msg.Path)
	if err != nil {
		return nil, connect.NewError(connect.CodeInternal, err)
	}

	return connect.NewResponse(&r2t4v1.RegisterPluginResponse{
		Plugin: plugin,
	}), nil
}

// UnregisterPlugin removes a plugin.
func (h *PluginHandler) UnregisterPlugin(
	ctx context.Context,
	req *connect.Request[r2t4v1.UnregisterPluginRequest],
) (*connect.Response[r2t4v1.UnregisterPluginResponse], error) {
	err := h.manager.UnregisterPlugin(req.Msg.PluginId)
	if err != nil {
		return nil, connect.NewError(connect.CodeNotFound, err)
	}

	return connect.NewResponse(&r2t4v1.UnregisterPluginResponse{
		Success: true,
	}), nil
}

// SetPluginStatus enables or disables a plugin.
func (h *PluginHandler) SetPluginStatus(
	ctx context.Context,
	req *connect.Request[r2t4v1.SetPluginStatusRequest],
) (*connect.Response[r2t4v1.SetPluginStatusResponse], error) {
	plugin, err := h.manager.SetPluginStatus(req.Msg.PluginId, req.Msg.Enabled)
	if err != nil {
		return nil, connect.NewError(connect.CodeNotFound, err)
	}

	return connect.NewResponse(&r2t4v1.SetPluginStatusResponse{
		Plugin: plugin,
	}), nil
}

// TestPlugin tests a plugin handshake.
func (h *PluginHandler) TestPlugin(
	ctx context.Context,
	req *connect.Request[r2t4v1.TestPluginRequest],
) (*connect.Response[r2t4v1.TestPluginResponse], error) {
	success, msg, latency, err := h.manager.TestPlugin(req.Msg.PluginId)
	if err != nil {
		// Even if error, we return it in response for the UI to show
		return connect.NewResponse(&r2t4v1.TestPluginResponse{
			Success:   false,
			Message:   err.Error(),
			LatencyMs: latency,
		}), nil
	}

	return connect.NewResponse(&r2t4v1.TestPluginResponse{
		Success:   success,
		Message:   msg,
		LatencyMs: latency,
	}), nil
}
