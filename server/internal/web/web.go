// Package web provides the embedded admin web UI.
package web

import (
	"embed"
	"io/fs"
)

//go:embed index.html
var content embed.FS

// GetFS returns the embedded filesystem containing the admin UI.
func GetFS() fs.FS {
	return content
}
