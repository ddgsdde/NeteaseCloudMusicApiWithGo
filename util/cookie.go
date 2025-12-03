package util

import (
	"net/http"
	"github.com/gin-gonic/gin"
)

func SetCookies(c *gin.Context, cookies []*http.Cookie) {
	for _, cookie := range cookies {
		c.SetCookie(cookie.Name, cookie.Value, 60*60*24, "", cookie.Domain, false, false)
	}
}
