package service

import (
	"github.com/gin-gonic/gin"
	"singo/util"
)

type LoginQrCheckService struct {
	Key string `form:"key"`
}

func (service *LoginQrCheckService) LoginQrCheck(c *gin.Context) map[string]interface{} {
	cookies := c.Request.Cookies()
	options := &util.Options{
		Crypto: "weapi",
		Ua:     "pc",
		Cookies: cookies,
	}
	data := make(map[string]string)
	data["key"] = service.Key
	data["type"] = "1"

	reBody, respCookies := util.CreateRequest("POST", "https://music.163.com/weapi/login/qrcode/client/login", data, options)

	cookiesStr := ""
	for _, cookie := range respCookies {
		if cookiesStr != "" {
			cookiesStr = cookiesStr + ";"
		}
		cookiesStr = cookiesStr + cookie.String()
		// Set cookie in response for the client to hold onto
		c.SetCookie(cookie.Name, cookie.Value, 60*60*24*30, "/", "", false, false)
	}
	reBody["cookie"] = cookiesStr
	return reBody
}
