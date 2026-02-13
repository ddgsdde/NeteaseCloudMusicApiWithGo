package api

import (
	"github.com/gin-gonic/gin"
	"singo/service"
)

// 二维码 key 生成接口
func LoginQrKey(c *gin.Context) {
	var service service.LoginQrKeyService
	if err := c.ShouldBind(&service); err == nil {
		res := service.LoginQrKey(c)
		c.JSON(200, res)
	} else {
		c.JSON(200, ErrorResponse(err))
	}
}

// 二维码生成接口
func LoginQrCreate(c *gin.Context) {
	var service service.LoginQrCreateService
	if err := c.ShouldBind(&service); err == nil {
		res := service.LoginQrCreate(c)
		c.JSON(200, res)
	} else {
		c.JSON(200, ErrorResponse(err))
	}
}

// 二维码检测接口
func LoginQrCheck(c *gin.Context) {
	var service service.LoginQrCheckService
	if err := c.ShouldBind(&service); err == nil {
		res := service.LoginQrCheck(c)
		c.JSON(200, res)
	} else {
		c.JSON(200, ErrorResponse(err))
	}
}
