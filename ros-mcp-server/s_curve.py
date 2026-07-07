import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import time

urscript = """def s_curve():
  p0 = get_actual_tcp_pose()
  movel(pose_trans(p0, p[0.0, 0.03, 0.02, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
  movel(pose_trans(p0, p[0.0, 0.04, 0.04, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
  movel(pose_trans(p0, p[0.0, 0.03, 0.06, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
  movel(pose_trans(p0, p[0.0, 0.00, 0.08, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
  movel(pose_trans(p0, p[0.0, -0.03, 0.10, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
  movel(pose_trans(p0, p[0.0, -0.04, 0.12, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
  movel(pose_trans(p0, p[0.0, -0.03, 0.14, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
  movel(pose_trans(p0, p[0.0, 0.00, 0.16, 0, 0, 0]), a=0.2, v=0.1, r=0.0)
end
"""

def main():
    rclpy.init()
    node = rclpy.create_node('s_curve_publisher')
    pub = node.create_publisher(String, '/urscript_interface/script_command', 10)
    msg = String()
    msg.data = urscript
    
    # Wait for subscribers to connect
    time.sleep(1.0)
    
    pub.publish(msg)
    node.get_logger().info("Published URScript for S-curve")
    
    time.sleep(1.0)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
