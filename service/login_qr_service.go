package service

import (
	"github.com/gin-gonic/gin"
	"net/http"
	"singo/util"
)

type LoginQrKeyService struct{}

func (service *LoginQrKeyService) LoginQrKey(c *gin.Context) map[string]interface{} {
	cookies := c.Request.Cookies()
	cookiesOS := &http.Cookie{Name: "os", Value: "pc"}
	cookies = append(cookies, cookiesOS)

	options := &util.Options{
		Crypto:  "weapi",
		Ua:      "pc",
		Cookies: cookies,
	}
	data := make(map[string]string)
	data["type"] = "1"

	reBody, cookies := util.CreateRequest("POST", `https://music.163.com/weapi/login/qrcode/unikey`, data, options)

	cookiesStr := ""
	for _, cookie := range cookies {
		if cookiesStr != "" {
			cookiesStr = cookiesStr + ";"
		}
		cookiesStr = cookiesStr + cookie.String()
		c.SetCookie(cookie.Name, cookie.Value, 60*60*24, "", cookie.Domain, false, false)
	}
	if reBody["code"] == nil {
		reBody["cookie"] = cookiesStr
	}

	return reBody
}

type LoginQrCreateService struct {
	Key string `json:"key" form:"key"`
}

func (service *LoginQrCreateService) LoginQrCreate(c *gin.Context) map[string]interface{} {
	// Normally this returns just the data to generate QR code.
	// We can return the url directly.
	url := "https://music.163.com/login?codekey=" + service.Key
	return map[string]interface{}{
		"code": 200,
		"data": map[string]interface{}{
			"qrurl": url,
			"qrimg": "", // Optional: generate base64 image if needed, but url is usually enough
		},
	}
}

type LoginQrCheckService struct {
	Key string `json:"key" form:"key"`
}

func (service *LoginQrCheckService) LoginQrCheck(c *gin.Context) map[string]interface{} {
	cookies := c.Request.Cookies()
	cookiesOS := &http.Cookie{Name: "os", Value: "pc"}
	cookies = append(cookies, cookiesOS)

	options := &util.Options{
		Crypto:  "weapi",
		Ua:      "pc",
		Cookies: cookies,
	}
	data := make(map[string]string)
	data["key"] = service.Key
	data["type"] = "1"

	reBody, cookies := util.CreateRequest("POST", `https://music.163.com/weapi/login/qrcode/client/login`, data, options)

	cookiesStr := ""
	for _, cookie := range cookies {
		if cookiesStr != "" {
			cookiesStr = cookiesStr + ";"
		}
		cookiesStr = cookiesStr + cookie.String()
		// Important: If login success (803), we need to set the cookies.
		// Usually Netease returns cookies in the response headers.
		c.SetCookie(cookie.Name, cookie.Value, 60*60*24, "", cookie.Domain, false, false)
	}

	reBody["cookie"] = cookiesStr

	return reBody
}
